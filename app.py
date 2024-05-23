from flask import Flask, render_template, request, redirect, url_for
import os
from werkzeug.utils import secure_filename
import boto3

app = Flask(__name__)

BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

@app.route('/')
def index():
    return render_template('upload.html')

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
        
        s3 = boto3.client("s3", region_name="us-east-1")

        with open(filepath, "rb") as f:
            s3.upload_fileobj(f, BUCKET_NAME, "test_file.jpg")
        
        return 'File uploaded successfully'


# Main code
if __name__ == '__main__':
  port = int(os.environ.get('PORT', 5000))
  app.run(host='0.0.0.0', port = port)