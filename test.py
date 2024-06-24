import boto3
import os
from dotenv import load_dotenv
load_dotenv()

BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
PROFILE = os.getenv("PROFILE")
REGION = os.getenv("REGION")

print(f"Bucket: {BUCKET_NAME}")
print(f"Access Key: {ACCESS_KEY}")
print(f"Secret Key: {SECRET_KEY}")
print(f"Profile: {PROFILE}")
print(f"Region: {REGION}")

# Setting up the Boto3 session
session = boto3.Session(
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
    profile_name=PROFILE,
    region_name='us-east-1'
)
print(session)

s3 = session.client("s3")

try:
    with open("uploads/Concert.jpg", "rb") as f:
        s3.upload_fileobj(f, BUCKET_NAME, "test_file")
    print("Upload successful")
except Exception as e:
    print(f"An error occurred: {e}")
