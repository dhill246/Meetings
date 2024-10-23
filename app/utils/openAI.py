from dotenv import load_dotenv
from openai import OpenAI, OpenAIError
import subprocess
import os
from pathlib import Path
import time
from app.utils.mongo import get_prompts, add_meeting, get_meeting_data, get_all_one_on_ones, get_all_manager_meetings, get_general_meetings, get_all_employee_meetings, get_company_meetings
import json
from pydantic import create_model
from typing import List
from urllib.parse import urlparse
load_dotenv()
import logging

# Set up logging
logging.basicConfig(
    filename="meeting_summary.log",  # Log output to a file
    level=logging.DEBUG,  # Set the level of logging to DEBUG
    format="%(asctime)s - %(levelname)s - %(message)s"  # Customize log format
)

def create_meeting_summary_model(categories):
    fields = {}
    for category in categories:
        # Assuming all fields are strings; adjust the type as necessary
        fields[category] = (str, ...)
    MeetingSummary = create_model('MeetingSummary', **fields)
    return MeetingSummary

API_KEY = os.getenv("API_KEY")
client = OpenAI(api_key=API_KEY)

def transcribe_webm(full_path, username):

    try:
        # Attempt transcription
        with open(f"{full_path}", "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file
            )

    except OpenAIError as e:
        if "Invalid file format" in str(e):
            # Re-encode the file using FFmpeg
            temp_output_path = full_path.replace(".webm", "_reencoded.webm")
            subprocess.run([
                "ffmpeg", "-i", full_path, "-c:a", "libvorbis", temp_output_path
            ], check=True,  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Replace the original file with the re-encoded file
            os.replace(temp_output_path, full_path)

            # Retry transcription with the re-encoded file
            with open(full_path, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    model="whisper-1", 
                    file=audio_file
                )
        else:
            # Re-raise the exception if it's not related to file format
            raise e

    print("Grabbing transcription text")
    body = transcription.text

    path_parts = os.path.normpath(full_path).split(os.sep)
    tmp, webm, user, report, date, file = path_parts

    num = file.split(".")[0]

    folder_file_path = os.path.join(f"tmp_{username}", "transcribed_chunks", user, report, date)
    local_file_path = os.path.join(folder_file_path,  f"{num}.txt")

    if not os.path.exists(folder_file_path):
        os.makedirs(folder_file_path)

    # Write the text to the file
    with open(local_file_path, 'w', encoding="utf-8") as file:
        file.write(body)

def transcribe_mp4(video_filepath):
    try:
        # Extract audio from the video file
        audio_filepath = video_filepath.replace('.mp4', '.wav')

        # Use ffmpeg to extract audio
        subprocess.run([
            "ffmpeg", "-i", video_filepath, "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2", audio_filepath
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Transcribe the audio file using OpenAI's Whisper API
        with open(audio_filepath, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )

        transcription_text = transcription.text

        # Optionally, delete the audio file after transcription
        os.remove(audio_filepath)

        return transcription_text

    except OpenAIError as e:
        logging.error(f"Error transcribing MP4 file {video_filepath}: {e}")
        return ""

    except Exception as e:
        logging.error(f"Error processing MP4 file {video_filepath}: {e}")
        return ""


def summarize_meeting(input_file, output_file, username):
    with open(input_file, 'r', encoding="utf-8") as file:
        # Read the entire content of the file
        content = file.read()

    system_prompt = """Please analyze the following 1:1 meeting transcript and provide a detailed summary. The summary should include the following:
                        Tone of the Meeting: Describe the overall mood and atmosphere during the meeting. Was it collaborative, tense, productive, casual, etc.?
                        Key Takeaways: Identify the most important points discussed during the meeting. What were the main themes or topics covered?
                        Action Items: List all the action items that were agreed upon, including who is responsible for each and any deadlines mentioned.
                        Decisions Made: Highlight any decisions or agreements that were reached during the meeting. Include the rationale behind these decisions if discussed.
                        Concerns or Challenges: Note any concerns, challenges, or issues that were raised during the meeting, along with any proposed solutions or next steps.
                        Opportunities: Identify any potential opportunities that were discussed or hinted at during the meeting, whether for improvement, growth, or new initiatives.
                        Additional Notes: Include any other relevant information that could help in understanding the full context and outcomes of the meeting."""

    def generate_meeting_notes(temperature, system_prompt, model):
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": content
                }
            ]
        )

        return [response.choices[0].message.content, response.usage.prompt_tokens, response.usage.completion_tokens]
            
    model = "gpt-4o"

    transcribed_text, prompt_tokens, completion_tokens = generate_meeting_notes(0, system_prompt, model)


    folder_file_path = os.path.join(f"tmp_{username}", "summarized_meeting")
    local_file_path = os.path.join(folder_file_path,  output_file)

    if not os.path.exists(folder_file_path):
        os.makedirs(folder_file_path)

    # Write the text to the file
    with open(local_file_path, 'w') as file:
        file.write(transcribed_text)

def summarize_meeting_improved(input_file, output_file, username, org_name, org_id, type_name, meeting_name, user_id, attendees, meeting_duration):
    
    logging.debug(f"Function called with input_file={input_file}, output_file={output_file}, username={username}, org_name={org_name}, "
                  f"org_id={org_id}, type_name={type_name}, meeting_name={meeting_name}, user_id={user_id}, attendees={attendees}, "
                  f"meeting_duration={meeting_duration}")
    
    try:
        with open(input_file, 'r', encoding="utf-8") as file:
            content = file.read()
            logging.debug(f"Read content from input file {input_file}")
    except Exception as e:
        logging.error(f"Error reading input file {input_file}: {e}")
        return None

    try:
        system_prompt, categories = get_prompts(org_name=org_name,
                                                org_id=org_id,
                                                type_name=type_name,
                                                user_id=user_id)
        logging.debug(f"System prompt and categories generated: {system_prompt}, {categories}")
    except Exception as e:
        logging.error(f"Error generating prompts: {e}")
        return None

    try:
        MeetingSummary = create_meeting_summary_model(categories)
        logging.debug(f"MeetingSummary model created with categories: {categories}")
        
        # Log detailed structure of the MeetingSummary model
        meeting_summary_fields = {name: field for name, field in MeetingSummary.__fields__.items()}
        logging.debug(f"MeetingSummary model structure: {meeting_summary_fields}")

    except Exception as e:
        logging.error(f"Error creating MeetingSummary model: {e}")
        return None
    
    model = "gpt-4o-2024-08-06"
    temperature = 0

    try:
        logging.debug(f"Calling GPT model with system prompt and content.")
        response = client.beta.chat.completions.parse(
            model=model,
            temperature=temperature,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": content
                }
            ],
            response_format=MeetingSummary
        )
        message = response.choices[0].message
        logging.debug(f"Response received from GPT model.")

        if message.parsed:
            parsed_response = message.parsed
            parsed_dict = parsed_response.model_dump()
            logging.debug(f"Parsed response: {parsed_dict}")

            # Proceed to store in database
            add_meeting(org_name, org_id, content, parsed_dict, attendees, meeting_duration, type_name, meeting_name, collection_name="Meetings")
            logging.debug("Meeting successfully added to the database.")

            # Write the structured JSON to the file
            folder_file_path = os.path.join(f"tmp_{username}", "summarized_meeting")
            local_file_path = os.path.join(folder_file_path, output_file)

            if not os.path.exists(folder_file_path):
                os.makedirs(folder_file_path)
                logging.debug(f"Created directory {folder_file_path}")

            with open(local_file_path, 'w') as file:
                file.write(parsed_response.model_dump_json())
                logging.debug(f"Summarized meeting written to {local_file_path}")

            return parsed_dict

        elif message.refusal:
            logging.warning("Model refused to provide a response.")
            return None

    except OpenAIError.LengthFinishReasonError:
        logging.error("Response was cut off due to max tokens. Consider increasing 'max_tokens'.")
        return None
    except Exception as e:
        logging.error(f"An error occurred during the GPT request or response handling: {e}")
        return None



def generate_ai_reply(messages, page_url, user_id, org_name, org_id):

    content = "Please help the user answer the question they ask using the following data. Answer the question thouroughly, but in as few sentences as possible. No bullet points or lists."

    # Parse the URL
    parsed_url = urlparse(page_url)
    url_parts = parsed_url.path.strip("/").split("/")

    if url_parts[0] == "home":
        if url_parts[1] == "view_meeting":
            meeting_id = url_parts[2]

            meeting_data = get_meeting_data(org_name, org_id, meeting_id)

            summary = str(meeting_data['summary'])

            try:
                text = str(meeting_data['raw_text'])
            except Exception as e:
                text = ""

            content += summary + " " + text

        if url_parts[1] == "meetings":

            if url_parts[2] == "oneonone":
                report_id = int(url_parts[3])

                report_data = list(get_all_one_on_ones(org_name, org_id, report_id))

                content += str(report_data)

            if url_parts[2] == "generalmeetings":

                meeting_type = url_parts[3]
                meeting_type = meeting_type.replace("_", " ")

                attendee_info = {"user_id": user_id}

                general_meeting_data = list(get_general_meetings(meeting_type, org_name, org_id, attendee_info))


                print(general_meeting_data)
                content += str(general_meeting_data)

    elif url_parts[0] == "admin":
        if url_parts[1] == "reports":
            report_id = url_parts[2]

            report_data = list(get_all_one_on_ones(org_name, org_id, report_id))

            content += str(report_data)

        elif url_parts[1] == "oneonones":
            manager_id = int(url_parts[2])

            attendee_info = {"manager_id": manager_id}

            report_data = list(get_all_manager_meetings(org_name, org_id, attendee_info))

            content += str(report_data)

        elif url_parts[1] == "employee":
            employee_id = int(url_parts[2])

            attendee_info = {"employee_id": employee_id}

            report_data = list(get_all_employee_meetings(org_name, org_id, attendee_info))

            content += str(report_data)

        elif url_parts[1] == "specific_meeting":
            meeting_id = url_parts[2]

            meeting_data = get_meeting_data(org_name, org_id, meeting_id)

            summary = str(meeting_data['summary'])

            try:
                text = str(meeting_data['raw_text'])
            except Exception as e:
                text = ""

            content += summary + " " + text

        elif url_parts[1] == "dashboard":
            whole_company = list(get_company_meetings(org_name, org_id))

            content += str(whole_company)

        else:
            manager_id = int(url_parts[1])

            attendee_info = {"manager_id": manager_id}

            report_data = list(get_all_manager_meetings(org_name, org_id, attendee_info))

            content += str(report_data)



    ai_messages = [
        {"role": "system", "content": content},
    ]

    for msg in messages:
        role = "user" if msg['sender'] == 'user' else "assistant"
        ai_messages.append({"role": role, "content": msg['text']})

    model = "gpt-4o"
    temperature = 0

    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=ai_messages
    )

    ai_assistance, prompt_tokens, completion_tokens = [response.choices[0].message.content, response.usage.prompt_tokens, response.usage.completion_tokens]

    return ai_assistance

def generate_ai_reply_for_meeting(prompt, meeting_id, user_id, org_name, org_id):

    content = "The user will ask a question about a given meeting. Please provide a 2-3 sentence response to the user's question."

    meeting_data = get_meeting_data(org_name, org_id, meeting_id)

    content += " " + str(meeting_data['raw_text'])

    content += " " + str(prompt)

    ai_messages = [
        {"role": "system", "content": content},
    ]

    model = "gpt-4o"
    temperature = 0

    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=ai_messages
    )

    ai_assistance, prompt_tokens, completion_tokens = [response.choices[0].message.content, response.usage.prompt_tokens, response.usage.completion_tokens]

    return ai_assistance