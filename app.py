from flask import Flask, render_template, request, redirect, url_for
from flask_socketio import SocketIO, emit
import os
import subprocess
import boto3
from io import BytesIO
import logging

# Set up basic logging
# logging.basicConfig(level=logging.DEBUG)

# Specify path to ffmpeg
# TODO -- Figure out how to package ffmpeg for use on Heroku server
ffmpeg_path = r'C:\Program Files\ffmpeg\bin\ffmpeg.exe'  # Adjust the path according to your actual ffmpeg installation

# Function to convert a .webm file into a .wav file
# TODO -- Move this into a helper folder
def convert_to_wav(input_file, output_file):
    # Fmmpeg ommand to convert the input file to WAV format
    command = [ffmpeg_path, '-i', input_file, output_file]

    try:
        # Execute the command and capture output
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Check if the command was successful
        if result.returncode != 0:
            # Output error if ffmpeg failed
            print("ffmpeg error:", result.stderr)
        else:
            print("Conversion successful:", result.stdout)

    except FileNotFoundError:
        print("ffmpeg not found. Ensure it is installed and added to your PATH.")
    except Exception as e:
        print("An error occurred:", str(e))

# Connect to S3
# Initialize S3 client globally if possible (outside the request handling logic)
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv('BUCKETEER_AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('BUCKETEER_AWS_SECRET_ACCESS_KEY'),
)

bucket_name = os.getenv('BUCKETEER_BUCKET_NAME')

# Initialize Flask app
app = Flask(__name__)

# Initialize socket for listening
socketio = SocketIO(app)

# Set the directory to store audio files
AUDIO_FOLDER = 'audio_files'
os.makedirs(AUDIO_FOLDER, exist_ok=True)

@app.route('/', methods=["GET", "POST"])
def index():
    if request.method == "POST":
        username = request.form['username']
        date = request.form['date']
        return redirect(url_for('record', username=username, date=date))
    return render_template('index.html')

@app.route('/record')
def record():
    username = request.args.get('username', '')
    date = request.args.get('date', '')
    return render_template('record.html', username=username, date=date)

@socketio.on('audio_chunk')
def handle_audio_chunk(data):
    app.logger.info('BROCCOLI THOUGHTS')
    name = data['username']
    date = data['date']
    audio = data["audioData"]

    # Create a unique file path or identifier
    file_identifier = f"{name}_{date}.webm"  # Change file extension based on your data format

    # Use BytesIO to handle file in memory
    audio_buffer = BytesIO()
    audio_buffer.write(audio)

    # Set the cursor to the beginning of the stream
    audio_buffer.seek(0)

    # Upload to S3
    try:
        s3_client.upload_fileobj(audio_buffer, bucket_name, file_identifier)
        print("Upload successful")
    except Exception as e:
        print(f"Failed to upload: {e}")
    finally:
        audio_buffer.close()

# @socketio.on('audio_end')
# def handle_audio_end(data):
#     name = data['username']
#     date = data['date']
#     file_path = f"{name}_{date}.webm"

#     # Instead of storing locally, fetch the file from S3
#     obj = s3_client.get_object(Bucket=bucket_name, Key=file_path)
#     audio_body = obj['Body'].read()
    
#     # You can convert the file using a temporary local file or in-memory
#     with open(f"/tmp/{name}_{date}.webm", 'wb') as f:
#         f.write(audio_body)

#     input_file = f"/tmp/{name}_{date}.webm"
#     output_file = f"/tmp/{name}_{date}.wav"
    
#     # Convert to WAV as before
#     convert_to_wav(input_file, output_file)
    
#     # Optionally, upload the WAV file back to S3
#     with open(output_file, 'rb') as f:
#         s3_client.upload_fileobj(f, bucket_name, f"{name}_{date}.wav")

#     files_in_bucket = list_files(bucket_name)
#     # Writing the output to a text file
#     with open("/mnt/data/S3_bucket_contents.txt", "w") as f:
#         f.write("Files in Bucket:\n")
#         for file_name in files_in_bucket:
#             f.write(f"{file_name}\n")

audio_streams = {}

@socketio.on('audio_chunk')
def handle_audio_chunk(data):
    name = data['username']
    date = data['date']
    audio = data["audioData"]

    key = f"{name}_{date}"

    # Check if the stream already exists, if not, create a new BytesIO stream
    if key not in audio_streams:
        audio_streams[key] = BytesIO()
    
    # Append audio chunk to the stream
    audio_streams[key].write(audio)

    # file_path = os.path.join(AUDIO_FOLDER, f"{name}_{date}.webm")  # Change file extension based on your data format

    # # Write the chunk to a file
    # with open(file_path, 'ab') as f:  # 'ab' opens the file in append mode as binary
    #     f.write(audio)

@socketio.on('audio_end')
def handle_audio_end(data):
    name = data['username']
    date = data['date']

    key = f"{name}_{date}"

    # Get the BytesIO stream
    audio_stream = audio_streams.pop(key, None)

    if audio_stream:
        # Reset the pointer of the BytesIO object to the beginning
        audio_stream.seek(0)
        
        # Define the S3 key
        s3_key = f"audio_files/{key}.webm"  # or ".wav" if you convert before uploading

        # Upload the file to S3
        s3_client.upload_fileobj(audio_stream, bucket_name, s3_key)
        
        # Close the stream
        audio_stream.close()

    # input_file = os.path.join(AUDIO_FOLDER, f"{name}_{date}.webm")
    # output_file = os.path.join(AUDIO_FOLDER, f"{name}_{date}.wav")
    # convert_to_wav(input_file, output_file)

    # key = f"audio_files/{name}_{date}.wav"

    # s3_client.upload_file(output_file, bucket_name, key)

if __name__ == '__main__':
    socketio.run(app, allow_unsafe_werkzeug=True)
