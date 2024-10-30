from celery import Celery
import os
import shutil
import logging
import time
from celery.signals import worker_shutdown
import boto3
from app.utils.openAI import transcribe_webm, transcribe_mp4, summarize_meeting_improved
from app.utils.JoinTranscriptions import combine_text_files, json_to_word
from app.utils.s3_utils import upload_file_to_s3, download_file, list_files, delete_from_s3
from app.utils.Emails import send_email_to_user
from dotenv import load_dotenv
from moviepy.editor import VideoFileClip
from app.models import Organization, User, BotRecord, db
import json
import re
from datetime import datetime
load_dotenv()
import sys

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

def get_video_duration(video_filepath):
    try:
        clip = VideoFileClip(video_filepath)
        duration = clip.duration  # duration in seconds
        clip.close()
        return duration
    except Exception as e:
        logger.error(f"Error getting duration of video {video_filepath}: {e}")
        return 0

@app.task
def dummy_task():
    # Write a function that writes out a text file
    with open("dummy_task.txt", "w") as f:
        f.write("This is a dummy task.")
    logger.info("Dummy task executed.")

@app.task
def do_file_conversions(attendees_info, meeting_type, meeting_name, meeting_duration, date, org_name, org_id):

    logger.info("ARGS:\n")
    logger.info("Attendees: " + str(attendees_info))
    logger.info("Meeting Type: " + str(meeting_type))
    logger.info("Meeting Name: " + str(meeting_name))
    logger.info("Meeting Duration: " + str(meeting_duration))
    logger.info("Date: " + str(date))
    logger.info("Org Name: " + str(org_name))
    logger.info("Org ID: " + str(org_id))

    emails = [person_info["email"] for person_info in attendees_info]

    if meeting_type == "One-on-One":
        manager_info, report_info = attendees_info

        user_id = manager_info["user_id"]

        meeting_title = f"{meeting_type} Meeting with {manager_info['first_name']} {manager_info['last_name']} and {report_info['first_name']} {report_info['last_name']} on {date}"
        report = f"{report_info['first_name']}{report_info['last_name']}"

        username = f"{manager_info['first_name']} {manager_info['last_name']}"
        
        filepath_to_convert = os.path.join(username, report, date)
        print("Filepath to convert", filepath_to_convert)
        filepath_to_convert = filepath_to_convert.replace("\\", "_")
        filepath_to_convert = filepath_to_convert.replace("/", "_")

        logger.info(f"Starting file process for path: {filepath_to_convert}")
        
        try:
            files = list_files(BUCKET_NAME, filepath_to_convert)
            logger.info(f"Found {len(files)} files to process.")

            if len(files) != 0:

                for item in files:
                    user, report, date, file = item.split("_")

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
                # summarize_meeting(raw_text_path, output_file, username)
                print("Arguments for summarizing meeting: ", raw_text_path, output_file, username, org_name, org_id, meeting_type)
                json_data = summarize_meeting_improved(raw_text_path, output_file, username, org_name, org_id, meeting_type, meeting_name, user_id, attendees_info, meeting_duration)
                logger.info(f"JSON DATA: {json_data}")
                logger.info(f"Successfully summarized: {raw_text_path}.")

                summarized_meeting_path = os.path.join(f"tmp_{username}", "summarized_meeting", output_file)
                # word_doc_path = summary_to_word_doc(summarized_meeting_path, username)
                word_doc_path = json_to_word(summarized_meeting_path, username, json_data, meeting_title)
                logger.info(f"Successfully turned: {summarized_meeting_path} into a word document.")

                print("Sending email")

                for email in emails:
                    send_email_to_user(word_doc_path, meeting_title, email)

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

    else:

        manager_info = attendees_info[0]

        user_id = manager_info["user_id"]

        meeting_title = f"{meeting_type} hosted by {manager_info['first_name']} {manager_info['last_name']} on {date}"
        report = meeting_type

        username = f"{manager_info['first_name']} {manager_info['last_name']}"
        
        filepath_to_convert = os.path.join(username, report, date)
        filepath_to_convert = filepath_to_convert.replace("\\", "_")
        filepath_to_convert = filepath_to_convert.replace("/", "_")

        logger.info(f"Starting file process for path: {filepath_to_convert}")
        
        try:
            files = list_files(BUCKET_NAME, filepath_to_convert)
            logger.info(f"Found {len(files)} files to process.")

            if len(files) != 0:

                for item in files:
                    user, report, date, file = item.split("_")

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
                # summarize_meeting(raw_text_path, output_file, username)
                print("Arguments for summarizing meeting: ", raw_text_path, output_file, username, org_name, org_id, meeting_type)
                json_data = summarize_meeting_improved(raw_text_path, output_file, username, org_name, org_id, meeting_type, meeting_name, user_id, attendees_info, meeting_duration)
                logger.info(f"Successfully summarized: {raw_text_path}.")

                summarized_meeting_path = os.path.join(f"tmp_{username}", "summarized_meeting", output_file)
                # word_doc_path = summary_to_word_doc(summarized_meeting_path, username)
                word_doc_path = json_to_word(summarized_meeting_path, username, json_data, meeting_title)
                logger.info(f"Successfully turned: {summarized_meeting_path} into a word document.")

                print("Sending email")

                for email in emails:
                    send_email_to_user(word_doc_path, meeting_title, email)

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


@app.task
def process_recall_video(video_filepath, bot_id, meeting_type, user, org, meeting_name):
    try:
        logger.info(f"Processing video for bot {bot_id}")

        org_name = org["name"]

        # Function to sanitize filenames and directory names
        def sanitize_filename(s):
            return re.sub(r'[<>:"/\\|?*]', '_', s)

        # Sanitize 'username' and 'meeting_name' for use in file paths
        username = sanitize_filename(f"{user['first_name']} {user['last_name']}")
        meeting_name_sanitized = sanitize_filename(meeting_name)
        date = datetime.now().strftime('%Y-%m-%d')

        # Create a temporary working directory
        tmp_folder = f"tmp_{username}"
        os.makedirs(tmp_folder, exist_ok=True)

        # Copy the video file into the temporary directory
        video_folder = os.path.join(tmp_folder, 'video_files')
        os.makedirs(video_folder, exist_ok=True)
        video_filename = os.path.basename(video_filepath)
        tmp_video_filepath = os.path.join(video_folder, video_filename)

        shutil.copy2(video_filepath, tmp_video_filepath)
        logger.info(f"Copied video file to {tmp_video_filepath}")

        # Now, use the video file from the temporary directory
        # Transcribe the MP4 file
        transcription_text = transcribe_mp4(tmp_video_filepath)

        if not transcription_text:
            logger.error(f"No transcription text obtained for video {tmp_video_filepath}")
            return

        # Save transcription text to a file within the temporary directory
        output_filename = f"{username}_{meeting_name_sanitized}_{date}.txt"
        transcription_folder = os.path.join(tmp_folder, 'transcribed_chunks', username, meeting_name_sanitized, date)
        os.makedirs(transcription_folder, exist_ok=True)
        transcription_filepath = os.path.join(transcription_folder, output_filename)

        with open(transcription_filepath, 'w', encoding='utf-8') as f:
            f.write(transcription_text)

        logger.info(f"Transcription saved to {transcription_filepath}")

        # Prepare raw text path
        raw_text_folder = os.path.join(tmp_folder, 'joined_text')
        os.makedirs(raw_text_folder, exist_ok=True)
        raw_text_path = os.path.join(raw_text_folder, output_filename)
        shutil.copyfile(transcription_filepath, raw_text_path)

        # Generate meeting summary
        meeting_duration = get_video_duration(tmp_video_filepath)
        json_data = summarize_meeting_improved(
            raw_text_path,
            output_filename,
            username,
            org_name,
            org["org_id"],
            type_name=meeting_type,
            meeting_name=meeting_name_sanitized,
            user_id=user["user_id"],
            attendees=[user],  # Assuming attendees_info expects a list
            meeting_duration=meeting_duration
        )

        # Save the summary JSON data within the temporary directory
        summarized_meeting_folder = os.path.join(tmp_folder, 'summarized_meeting')
        os.makedirs(summarized_meeting_folder, exist_ok=True)
        summarized_meeting_filepath = os.path.join(summarized_meeting_folder, output_filename.replace('.txt', '.json'))

        with open(summarized_meeting_filepath, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2)

        logger.info(f"Meeting summary saved to {summarized_meeting_filepath}")

        # Generate Word document from the summary
        meeting_title = f"{meeting_name_sanitized} on {date}"
        word_doc_path = json_to_word(summarized_meeting_filepath, username, json_data, meeting_title)

        logger.info(f"Word document created at {word_doc_path}")

        # Send email to the user with the Word document
        send_email_to_user(word_doc_path, meeting_title, user["email"])

        logger.info(f"Email sent to {user['email']} with the meeting summary")

        # Upload raw text to S3
        upload_path = "Transcription_" + output_filename
        upload_file_to_s3(raw_text_path, upload_path)
        logger.info(f"Successfully uploaded: {raw_text_path} to S3 as {upload_path}.")

        # Upload summarized text to S3
        upload_path = "Summary_" + output_filename
        upload_file_to_s3(summarized_meeting_filepath, upload_path)
        logger.info(f"Successfully uploaded: {summarized_meeting_filepath} to S3 as {upload_path}.")

        # Clean up the temporary working directory
        logger.info(f"Attempting to delete {tmp_folder} folder:")
        safe_delete_folder(tmp_folder)
        logger.info(f"Successfully deleted {tmp_folder} folder.")

        # Optionally delete the original video file if no longer needed
        # os.remove(video_filepath)

    except Exception as e:
        logger.error(f"Error processing video for bot {bot_id}: {e}")

@worker_shutdown.connect
def worker_shutdown_handler(**kwargs):
    # Add your cleanup code here
    app.control.shutdown()  # Gracefully shutdown Celery
    os._exit(0)  # Force exit to ensure all connections are closed