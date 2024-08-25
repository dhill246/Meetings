from celery import Celery
import os
import shutil
import logging
import time
from celery.signals import worker_shutdown
import boto3
from app.utils.openAI import transcribe_webm, summarize_meeting
from app.utils.JoinTranscriptions import combine_text_files, summary_to_word_doc
from app.utils.s3_utils import upload_file_to_s3, download_file, list_files, delete_from_s3
from app.utils.Emails import send_email_to_user

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Celery('tasks', broker=os.getenv("CLOUDAMQP_URL"))

app.conf.update(broker_connection_retry_on_startup=True,
                broker_pool_limit=1,
                worker_concurrency=1,
                timezone="UTC",
                enable_utc=True, 
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

def delete_folder(folder_path):
    """Delete a folder and its contents after ensuring all files are closed."""
    try:
            # Ensure the directory exists
        if os.path.exists(folder_path):
            # Remove the directory and its contents
            shutil.rmtree(folder_path)

    except Exception as e:
        logger.error(f"An error occurred: {e}")
    
def safe_delete_folder(folder_path, retries=3, delay=5):
    """Attempt to safely delete a folder with retries and delay."""
    for attempt in range(retries):
        try:
            delete_folder(folder_path)
            break
        except Exception as e:
            time.sleep(delay)
    else:
        logger.error(f"Failed to delete folder {folder_path} after {retries} attempts")

@app.task
def do_file_conversions(username, firstname, lastname, date, emails):
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
                temp_download_folder = os.path.join(f"tmp_{username}", "downloaded_webm_file")
                temp_transcribed_folder = os.path.join(f"tmp_{username}", "transcribed_chunks")
                
                full_webm_path = os.path.join(temp_download_folder, user, report, date, file)
                transcribe_webm(full_webm_path, username)
                logger.info(f"Successfully transcribed file: {item} into text.")


            input_folder = os.path.join(f"tmp_{username}", "transcribed_chunks", username, report, date)
            output_file = f"{username}_{report}_{date}.txt"
            combine_text_files(input_folder, output_file, username)
            logger.info(f"Successfully combined all text file in {input_folder} into {output_file}")

            raw_text_path = os.path.join(f"tmp_{username}", "joined_text", output_file)
            summarize_meeting(raw_text_path, output_file, username)
            logger.info(f"Successfully summarized: {raw_text_path}.")

            summarized_meeting_path = os.path.join(f"tmp_{username}", "summarized_meeting", output_file)
            word_doc_path = summary_to_word_doc(summarized_meeting_path, username)
            logger.info(f"Successfully turned: {summarized_meeting_path} into a word document.")

            print("Sending email")

            for email in emails:
                send_email_to_user(word_doc_path, user, report, date, email)

            # Upload raw text to S3
            upload_path = "Transcription_" + output_file
            upload_file_to_s3(raw_text_path, upload_path)
            logger.info(f"Successfully uploaded: {raw_text_path} to S3 as {upload_path}.")

            # Upload summarized text to S3
            upload_path = "Summary_" + output_file
            upload_file_to_s3(summarized_meeting_path, upload_path)
            logger.info(f"Successfully uploaded: {summarized_meeting_path} to S3 as {upload_path}.")

            # Safely try deleting folder
            logger.info(f"Attempting to delete tmp_{username} folder:")
            safe_delete_folder(f"tmp_{username}")
            logger.info(f"Successfully deleted tmp_{username} folder.")

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