from flask import Flask, render_template, request, redirect, url_for
from flask_socketio import SocketIO, emit
import os
import boto3
from io import BytesIO
import logging


# Initialize Flask app
app = Flask(__name__)
# Initialize socket for listening
socketio = SocketIO(app)
# Set up basic logging output for the app
logging.basicConfig(level=logging.INFO)

# Initialize audio stream dict to hold audio even when paused
AUDIO_STREAMS = {}
bucket_name = os.getenv('BUCKETEER_BUCKET_NAME')
# Connect to S3 bucketeer
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv('BUCKETEER_AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('BUCKETEER_AWS_SECRET_ACCESS_KEY'),
)

@app.route('/', methods=["GET", "POST"])
def index():
    # If post request is sent, get the specified username and date
    # then proceed to the recording page
    # Otherwise return the index page
    if request.method == "POST":
        username = request.form['username']
        date = request.form['date']
        return redirect(url_for('record', username=username, date=date))
    return render_template('index.html')

@app.route('/record')
def record():
    # Save the username and date for passing to the recording template
    username = request.args.get('username', '')
    date = request.args.get('date', '')
    return render_template('record.html', username=username, date=date)

@socketio.on('audio_chunk')
def handle_audio_chunk(data):
    # When audio_chunk is sent by the client, which
    # happens frequently, get that data (webm file)
    key = data["key"]
    audio = data["audioData"]

    if audio != {}:
        # Create a BytesIO stream for this chunk
        audio_stream = BytesIO(audio)
        audio_stream.seek(0)

        # Log chunk size
        app.logger.info("Appending chunk of size %d to stream for key: %s", len(audio), key)
        
        # Upload the file to S3
        try:
            s3_client.upload_fileobj(audio_stream, bucket_name, key)
            app.logger.info("Upload succeeded for key: %s", key)
        except Exception as e:
            app.logger.error("Upload failed for key: %s with error: %s", key, e)
        
        audio_stream.close()


@socketio.on('audio_end')
def handle_audio_end(data):
    name = data['username']
    date = data['date']
    key_prefix = f"{name}_{date}"
    app.logger.info(f"Recording ended for {key_prefix}")

if __name__ == '__main__':
    socketio.run(app)
