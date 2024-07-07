from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit
from flask_migrate import Migrate
import os
import boto3
from io import BytesIO
import logging
from datetime import datetime
from models import db, User
from functools import wraps
# from utils.s3Uploads import check_existing_s3_files, upload_to_s3

# Initialize Flask app
app = Flask(__name__)

# Setting a secret key for secure sessions and cookies
app.secret_key = os.environ.get("SECRET_KEY")

# Initialize socket for listening
socketio = SocketIO(app)

# Set up basic logging output for the app
logging.basicConfig(level=logging.INFO)

# Database connection string
uri = os.environ['DATABASE_URL']
if uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri

# Disable SQLAlchemy event system to save resources
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize the database connection
db.init_app(app)

# Enable migration
migrate = Migrate(app, db)

# Create database tables that don't exist yet
with app.app_context():
    db.create_all()

# TODO -- Delete all this and fix bug that 
# releases audio when this gets moved
bucket_name = os.getenv('BUCKETEER_BUCKET_NAME')

# Connect to S3 bucketeer
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv('BUCKETEER_AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('BUCKETEER_AWS_SECRET_ACCESS_KEY'),
)

def check_existing_s3_files():
    response = s3_client.list_objects_v2(Bucket=bucket_name)
    list_of_files = []

    # Check if 'Contents' key is in the response (it won't be if the bucket is empty)
    if 'Contents' in response:
        for item in response['Contents']:
            print(item['Key'], item['LastModified'], item['Size'])
            list_of_files.append(item["Key"])

        return list_of_files
    else:
        print("No items in the bucket.")
        return []
    

def upload_to_s3(audio_stream, key, bucket_name=bucket_name):
    s3_client.upload_fileobj(audio_stream, bucket_name, key)

# Wrapper function to restrict access to pages
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

    
@app.route('/', methods=["GET", "POST"])
@login_required
def index():
    # If post request is sent, get the specified username and date
    # then proceed to the recording page
    # Otherwise return the index page

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
        # user = User.query.filter_by(username=username).first()
        # if user is not None and user.check_password(password):
        if username == os.getenv("BLENDER_USERNAME") and password == os.getenv("BLENDER_PASSWORD"):
            session['username'] = username
            return redirect(url_for('index'))
        else:
            return 'Invalid credentials'
    return render_template('login.html')

# @app.route('/register', methods=['GET', 'POST'])
# def register():
#     if request.method == 'POST':
#         username = request.form['username']
#         password = request.form['password']
#         firstname = request.form['firstname']
#         lastname = request.form['lastname']
#         user = User(username=username, firstname=firstname, lastname=lastname)
#         user.set_password(password)
#         db.session.add(user)
#         db.session.commit()
#         return redirect(url_for('login'))
#     return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))

@app.route('/record')
@login_required
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
                upload_to_s3(audio_stream, key)
                app.logger.info("Upload succeeded for key: %s", key)

            except Exception as e:
                app.logger.error("Upload failed for key: %s with error: %s", key, e)

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