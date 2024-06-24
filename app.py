from flask import Flask, render_template, request, redirect, url_for
from flask_socketio import SocketIO, emit
import os
import subprocess

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
    name = data['username']
    date = data['date']
    audio = data["audioData"]

    file_path = os.path.join(AUDIO_FOLDER, f"{name}_{date}.webm")  # Change file extension based on your data format

    # Write the chunk to a file
    with open(file_path, 'ab') as f:  # 'ab' opens the file in append mode as binary
        f.write(audio)

@socketio.on('audio_end')
def handle_audio_end(data):
    name = data['username']
    date = data['date']
    input_file = os.path.join(AUDIO_FOLDER, f"{name}_{date}.webm")
    output_file = os.path.join(AUDIO_FOLDER, f"{name}_{date}.wav")
    convert_to_wav(input_file, output_file)


if __name__ == '__main__':
    socketio.run(app, allow_unsafe_werkzeug=True)
