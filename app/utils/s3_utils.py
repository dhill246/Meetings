import os
import boto3
import traceback

bucket_name = os.getenv('BUCKETEER_BUCKET_NAME')

# Connect to S3 bucketeer
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv('BUCKETEER_AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('BUCKETEER_AWS_SECRET_ACCESS_KEY'),
)

def read_text_file(file_key):
    response = s3_client.get_object(Bucket=bucket_name, Key=file_key)
    file_content = response["Body"].read().decode("utf-8")

    return file_content


def list_files(bucket_name, prefix):
    """List files in an S3 bucket."""
    # List objects within the bucket
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
    list_of_files = []

    # Check if 'Contents' key is in the response (it won't be if the bucket is empty)
    if 'Contents' in response:
        for item in response['Contents']:
            list_of_files.append(item["Key"])
        return list_of_files
    else:
        return []

def download_file(bucket_name, item, user, report, date, file):
    """Download a file from S3."""
    # Local path where you want to save the downloaded file
    folder_file_path = os.path.join(f"tmp_{user}", "downloaded_webm_file", user, report, date)
    local_file_path = os.path.join(folder_file_path, file)

    if not os.path.exists(folder_file_path):
        os.makedirs(folder_file_path)
    
    # Download the file
    s3_client.download_file(bucket_name, item, local_file_path)

def check_existing_s3_files():
    response = s3_client.list_objects_v2(Bucket=bucket_name)
    list_of_files = []

    # Check if 'Contents' key is in the response (it won't be if the bucket is empty)
    if 'Contents' in response:
        for item in response['Contents']:
            list_of_files.append(item["Key"])

        return list_of_files
    else:
        print("No items in the bucket.")
        return []

def upload_audio_to_s3(audio_stream, key, bucket_name=bucket_name):
    """Upload audio to S3."""
    try:
        s3_client.upload_fileobj(audio_stream, bucket_name, key)
        print(f"File uploaded to {bucket_name}/{key}")
    except Exception as e:
        print(f"An error occurred: {e}")


def upload_file_to_s3(file_path, object_name, bucket_name=bucket_name):
    """Upload a file to S3."""
    try:
        with open(file_path, "rb") as file:
            s3_client.upload_fileobj(file, bucket_name, object_name)
        print(f"File {file_path} uploaded to {bucket_name}/{object_name}")
    except FileNotFoundError:
        print(f"The file {file_path} was not found")
    except Exception as e:
        print(f"An error occurred: {e}")
        print(traceback.format_exc())  # Log the full traceback


# def upload_to_s3(audio_stream, key, bucket_name=bucket_name):
#     s3_client.upload_fileobj(audio_stream, bucket_name, key)


def delete_from_s3(my_list=[]):
    if my_list != None:
        object_ids = [{'Key': item} for item in my_list]
        delete_params = {'Objects': object_ids}

        s3_client.delete_objects(Bucket=bucket_name, Delete=delete_params)

    else:
        print("No objects in bucket to delete.")