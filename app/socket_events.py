from flask_socketio import emit
from flask import current_app
from .utils.s3_utils import upload_audio_to_s3
from io import BytesIO
from .tasks import do_file_conversions


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
        print("Audio end socket message received.")
        name = data['username']
        date = data['date']
        firstname = data["firstname"]
        lastname = data["lastname"]
        key_prefix = f"{name}_{date}"

        # Start celery worker
        do_file_conversions.delay(name, firstname, lastname, date)

        
        print(f"Recording ended for {key_prefix}")