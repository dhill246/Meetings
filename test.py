import boto3
import os
from dotenv import load_dotenv
load_dotenv()

AUDIO_FOLDER = 'audio_files'
name = "Daniel"
date = "2024-06-26"

# Connect to S3
# Initialize S3 client globally if possible (outside the request handling logic)
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv('BUCKETEER_AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('BUCKETEER_AWS_SECRET_ACCESS_KEY'),
)

print(s3_client)

bucket_name = os.getenv('BUCKETEER_BUCKET_NAME')

def upload_test():
    output_file = os.path.join(AUDIO_FOLDER, "my_test_file.txt")


    key = f"audio_files/my_test_file.txt"

    s3_client.upload_file(output_file, bucket_name, key)

def list_test():
    # List objects within the bucket
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

def download_test(object_key, download_name):

    # Local path where you want to save the downloaded file
    local_file_path = os.path.join('C:\\Users\\Daniel Hill\\Documents\\HerokuNew', download_name)

    # Download the file
    s3_client.download_file(bucket_name, object_key, local_file_path)
    print(f"Downloaded file to {local_file_path}")

def delete_all_files():
    my_list = list_test()
    if my_list != None:
        object_ids = [{'Key': item} for item in my_list]
        delete_params = {'Objects': object_ids}

        s3_client.delete_objects(Bucket=bucket_name, Delete=delete_params)

    else:
        print("No objects in bucket to delete.")

# print(download_test("NOWAYTHISWORKS_2024-06-30/1.webm", "1.webm"))
# print(download_test("NOWAYTHISWORKS_2024-06-30/2.webm", "2.webm"))
# print(download_test("NOWAYTHISWORKS_2024-06-30/3.webm", "3.webm"))

print(delete_all_files())