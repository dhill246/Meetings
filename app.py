from flask import Flask, render_template, request, redirect, url_for
import os
from werkzeug.utils import secure_filename
import boto3

app = Flask(__name__)

BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
PROFILE = "danielthill"

# Setting up the Boto3 session
session = boto3.Session(
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
    profile_name=PROFILE,
    region_name='us-east-1'
)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)
    if file:
        filename = secure_filename(file.filename)
        
        filepath = os.path.join("uploads", filename)
        file.save(filepath)
        
        s3 = session.client("s3")

        with open(filepath, "rb") as f:
            s3.upload_fileobj(f, BUCKET_NAME, "test_file")
        
        return 'File uploaded successfully'


# Main code
if __name__ == '__main__':
  port = int(os.environ.get('PORT', 5000))
  app.run(host='0.0.0.0', port = port)