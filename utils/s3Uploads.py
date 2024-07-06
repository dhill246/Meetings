import os
import boto3

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