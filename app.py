from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit
import os
import boto3
from io import BytesIO
import logging
from datetime import datetime
from utils.s3Uploads import check_existing_s3_files, upload_to_s3
from rq import Queue
from s3_upload_worker import conn

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")

# Initialize redis queue for background jobs
q = Queue(connection=conn)

# Initialize socket for listening
socketio = SocketIO(app)
# Set up basic logging output for the app
logging.basicConfig(level=logging.INFO)
    
@app.route('/', methods=["GET", "POST"])
def index():
    # If post request is sent, get the specified username and date
    # then proceed to the recording page
    # Otherwise return the index page
    if "username" not in session:
        return redirect(url_for("login"))
    else:
        if request.method == "POST":
            username = request.form['username']
            firstname = request.form['firstname']
            lastname = request.form['lastname']

            # Get today's date
            today = datetime.now()

            # Format the date
            DATE = today.strftime("%m-%d-%Y")

            return redirect(url_for('record', username=username, firstname=firstname,
                                    lastname=lastname, date=DATE))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == os.getenv("BLENDER_USERNAME") and password == os.getenv("BLENDER_PASSWORD"):
            session['username'] = username
            return redirect(url_for('index'))
        else:
            return 'Invalid credentials'
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))

@app.route('/record')
def record():
    # Save the username and date for passing to the recording template
    username = request.args.get('username', '')
    date = request.args.get('date', '')
    firstname = request.args.get('firstname', '')
    lastname = request.args.get('lastname', '')

    list_s3 = check_existing_s3_files()
    list_s3 = set(["/".join(x.rsplit("/", 1)[:-1]) for x in list_s3])

    if f"{username}/{firstname}{lastname}/{date}" in list_s3:
        return render_template('error.html')

    else:
        return render_template('record.html', username=username, date=date, firstname=firstname, lastname=lastname)
    
@socketio.on('audio_chunk')
def handle_audio_chunk(data):
    app.logger.info("ENTERED AUDIO CHUNK")
    # When audio_chunk is sent by the client, which
    # happens frequently, get that data (webm file)
    key = data["key"]
    audio = data["audioData"]

    file_name = key.split("/")[-1]
    number = int(file_name.split(".")[0])

    if number < 260:

        if audio != {}:
            # Create a BytesIO stream for this chunk
            audio_stream = BytesIO(audio)
            audio_stream.seek(0)

            # Log chunk size
            app.logger.info("Appending chunk of size %d to stream for key: %s", len(audio), key)
            
            # Upload the file to S3
            try:
                job = q.enqueue(upload_to_s3, audio_stream, key)
                app.logger.info("Enqueued upload job for key: %s with job id: %s", key, job.get_id())

            except Exception as e:
                app.logger.error("Failed to enqueue upload job for key: %s with error: %s", key, e)

            audio_stream.close()

        else:
            app.logger.info("Audio file was empty.")

    else:
        app.logger.info("An audio file from a meeting longer than 65 minutes is trying to be uploaded. Blocking.")

@socketio.on('audio_end')
def handle_audio_end(data):
    name = data['username']
    date = data['date']
    key_prefix = f"{name}_{date}"
    app.logger.info(f"Recording ended for {key_prefix}")


if __name__ == '__main__':
    socketio.run(app)