from flask_socketio import disconnect
from flask import current_app, request
from app.models import User, Meeting
from .utils.s3_utils import upload_audio_to_s3
from .utils.Meetings import create_meeting
from io import BytesIO
from .tasks import do_file_conversions, dummy_task
from threading import Lock
from flask_jwt_extended import decode_token, verify_jwt_in_request, get_jwt_identity
import jwt
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# audio_end_lock = Lock()

def verify_jwt(token):
    try:
        claims = decode_token(token)
        return claims
    except jwt.InvalidTokenError:
        print("JWT INVALID")
        return None

def register_events(socketio):

    @socketio.on('connect')
    def test_connect():
        print("TRYING TO CONNECT")
        # try:
        #     # Manually extract token from request headers
        #     token = request.args.get("token")

        #     # If token is not provided, disconnect
        #     if not token:
        #         return disconnect()

        #     # Verify the token
        #     claims = verify_jwt(token)
        #     user_id = claims['sub']['user_id']

        #     print(f"Client connected with user ID: {user_id}")
        # except Exception as e:
        #     print(f"Connection failed: {str(e)}")
        #     return disconnect()

    @socketio.on('audio_chunk')
    def handle_audio_chunk(data):
        
        # When audio_chunk is sent by the client, which
        # happens frequently, get that data (webm file)
        key = data["key"]
        audio = data["audioData"]
        
        file_name = key.split("_")[-1]
        print(f"File name: {file_name}")
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
        # with audio_end_lock:
        if True:
            print("Audio end socket message received.")
            print("\n")
            print(data)
            print("\n")

            host_id = data["host_id"]
            attendees = data["attendees"]
            date = data['date']
            meeting_name = data["meeting_name"]

            # Query the database for emails associated with the given user_id and report_id
            host = User.query.filter_by(id=host_id).first()

            emails = []
            organization_id = None

            

            attendees = [{"first_name": "Travis", 
                          "last_name": "Starns", 
                          "email": "Travis.Starns@blenderproducts.com"}, 
                          {"first_name": "Dave", 
                           "last_name": "Dorste", 
                           "email": "Dave.Dorste@blenderproducts.com"}]

            if user:
                emails.append(user.email)  # Assuming the Users model has an 'email' field
            if report:
                emails.append(report.email)  # Adding the report's email

            # Start celery worker
            try:
                dummy_task.delay()
                do_file_conversions.delay(name, firstname, lastname, date, emails)
                logger.info("Celery task do_file_conversions started successfully.")
            except Exception as e:
                logger.error(f"Failed to start Celery task do_file_conversions: {e}")

            print(f"Recording ended for {meeting_name} with attendees: {attendees}")