from flask_socketio import emit
from flask import current_app
from app.models import User, Meeting
from .utils.s3_utils import upload_audio_to_s3
from .utils.Meetings import create_meeting
from io import BytesIO
from .tasks import do_file_conversions
from threading import Lock

audio_end_lock = Lock()


def register_events(socketio):

    @socketio.on('connect')
    def test_connect():
        print("Client connected")  # This will show in the terminal running your Flask app
        # current_app.logger.info("Client connected using app.logger")

    @socketio.on('audio_chunk')
    def handle_audio_chunk(data):
        
        # When audio_chunk is sent by the client, which
        # happens frequently, get that data (webm file)
        key = data["key"]
        audio = data["audioData"]

        file_name = key.split("/")[-1]
        number = int(file_name.split(".")[0])

        if number < 480:

            if audio:
                # Create a BytesIO stream for this chunk
                audio_stream = BytesIO(audio)
                audio_stream.seek(0)

                # Log chunk size
                print("Appending chunk of size %d to stream for key: %s", len(audio), key)
                
                # Upload the file to S3
                try:
                    upload_audio_to_s3(audio_stream, key)
                    print("Upload succeeded for key: %s", key)

                except Exception as e:
                    print("Upload failed for key: %s with error: %s", key, e)

                audio_stream.close()

            else:
                print("Audio file was empty.")

        else:
            print("An audio file from a meeting longer than 2 hours is trying to be uploaded. Blocking.")


    @socketio.on('audio_end')
    def handle_audio_end(data):
        with audio_end_lock:

            print("Audio end socket message received.")

            user_id = data["user_id"]
            report_id = data["report_id"]
            name = data['username']
            date = data['date']
            firstname = data["firstname"]
            lastname = data["lastname"]
            key_prefix = f"{name}_{date}"

            event_key = f"{data['user_id']}_{data['report_id']}_{data['date']}"

            # Query the database for emails associated with the given user_id and report_id
            user = User.query.filter_by(id=user_id).first()
            report = User.query.filter_by(id=report_id).first()

            emails = []

            if user:
                emails.append(user.email)  # Assuming the Users model has an 'email' field
            if report:
                emails.append(report.email)  # Adding the report's email

            # Start celery worker
            do_file_conversions.delay(name, firstname, lastname, date, emails)

            create_meeting(user_id, report_id, user.organization_id, f"Summary_{name}_{firstname}{lastname}_{date}.txt")

            print(f"Recording ended for {key_prefix}")