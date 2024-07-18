from celery import Celery
import os
import shutil
import logging
import time
from celery.signals import worker_shutdown
import boto3
from utils.openAI import transcribe_webm, summarize_meeting
from utils.JoinTranscriptions import combine_text_files, summary_to_word_doc
from utils.s3Uploads import upload_file_to_s3, download_file, list_files, delete_from_s3

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Celery('tasks', broker=os.getenv("CLOUDAMQP_URL"))

app.conf.update(broker_connection_retry_on_startup=True,
                broker_pool_limit=1,
                worker_concurrency=1, 
                task_serializer="json",
                prefetch_multiplier=1,
                worker_cancel_long_running_tasks_on_connection_loss=True)

BUCKET_NAME = os.getenv('BUCKETEER_BUCKET_NAME')

# Connect to S3 bucketeer
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv('BUCKETEER_AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('BUCKETEER_AWS_SECRET_ACCESS_KEY'),
)

@app.task
def write_out_some_text(text=""):
    logger.info(f"WRITING TEXT NOW")

    with open("HeresaFile.txt", "w") as f:
        f.write(text)

def delete_folder(folder_path="tmp/"):
    """Delete a folder and its contents after ensuring all files are closed."""
    try:
            # Ensure the directory exists
        if os.path.exists(folder_path):
            logger.info("Found tmp/ path. Trying to remove contents:")
            # Remove the directory and its contents
            shutil.rmtree(folder_path)
            logger.info(f"Folder {folder_path} successfully deleted")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
    
def safe_delete_folder(folder_path="tmp/", retries=3, delay=5):
    """Attempt to safely delete a folder with retries and delay."""
    for attempt in range(retries):
        logger.info(f"Trying to delete. Attempt number {attempt}")
        try:
            delete_folder(folder_path)
            break
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            time.sleep(delay)
    else:
        logger.error(f"Failed to delete folder {folder_path} after {retries} attempts")

@app.task
def do_file_conversions(username, firstname, lastname, date):
    report = f"{firstname}{lastname}"
    filepath_to_convert = os.path.join(username, report, date)
    filepath_to_convert = filepath_to_convert.replace("\\", "/")
    
    logger.info(f"Starting file process for path: {filepath_to_convert}")
    
    try:
        files = list_files(BUCKET_NAME, filepath_to_convert)
        logger.info(f"Found {len(files)} files to process.")

        if len(files) != 0:

            for item in files:
                user, report, date, file = item.split("/")

                # Download the file
                download_file(BUCKET_NAME, item, user, report, date, file)
                logger.info(f"Downloaded file: {item}")

                # Process the file (convert to .wav)
                temp_download_folder = os.path.join("tmp", "downloaded_webm_file")
                temp_transcribed_folder = os.path.join("tmp", "transcribed_chunks")
                
                full_webm_path = os.path.join(temp_download_folder, user, report, date, file)
                transcribe_webm(full_webm_path)
                logger.info(f"Successfully transcribed file: {item} into text.")


            input_folder = os.path.join("tmp", "transcribed_chunks", username, report, date)
            output_file = f"{username}_{report}_{date}.txt"
            combine_text_files(input_folder, output_file)
            logger.info(f"Successfully combined all text file in {input_folder} into {output_file}")

            raw_text_path = os.path.join("tmp", "joined_text", output_file)
            summarize_meeting(raw_text_path, output_file)
            logger.info(f"Successfully summarized: {raw_text_path}.")

            summarized_meeting_path = os.path.join("tmp", "summarized_meeting", output_file)
            summary_to_word_doc(summarized_meeting_path)
            logger.info(f"Successfully turned: {summarized_meeting_path} into a word document.")

            # EMAIL WORD DOC TO USER HERE
            # -- TODO
            # send_email_to_user()

            # Upload raw text to S3
            upload_path = "Transcription_" + output_file
            upload_file_to_s3(raw_text_path, upload_path)
            logger.info(f"Successfully uploaded: {raw_text_path} to S3 as {upload_path}.")

            # Upload summarized text to S3
            upload_path = "Summary_" + output_file
            upload_file_to_s3(summarized_meeting_path, upload_path)
            logger.info(f"Successfully uploaded: {summarized_meeting_path} to S3 as {upload_path}.")

            # Safely try deleting folder
            logger.info(f"Attempting to delete tmp/ folder:")
            safe_delete_folder()
            logger.info(f"Successfully deleted tmp/ folder.")

            # Destroy audio files in S3 bucket
            logger.info(f"Attempting to delete audio files from bucket:")
            delete_from_s3(files)
            logger.info(f"Successfully deleted audio files from bucket.")


    except Exception as e:
        logger.error(f"Error during file conversion process: {e}")


@worker_shutdown.connect
def worker_shutdown_handler(**kwargs):
    # Add your cleanup code here
    app.control.shutdown()  # Gracefully shutdown Celery
    os._exit(0)  # Force exit to ensure all connections are closed