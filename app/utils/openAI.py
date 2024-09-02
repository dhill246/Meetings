from dotenv import load_dotenv
from openai import OpenAI, OpenAIError
import subprocess
import os
from pathlib import Path
import time
from mongo import add_meeting
load_dotenv()

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


def summarize_meeting_improved(input_file, output_file, username, attendees):

    with open(input_file, 'r', encoding="utf-8") as file:
        # Read the entire content of the file
        content = file.read()

    # Define prompt:
    system_prompt = """Please analyze the following 1:1 meeting transcript and provide a detailed summary. The summary should include the following:
                        Tone of the Meeting: Describe the overall mood and atmosphere during the meeting. Was it collaborative, tense, productive, casual, etc.?
                        Key Takeaways: Identify the most important points discussed during the meeting. What were the main themes or topics covered?
                        Action Items: List all the action items that were agreed upon, including who is responsible for each and any deadlines mentioned.
                        Decisions Made: Highlight any decisions or agreements that were reached during the meeting. Include the rationale behind these decisions if discussed.
                        Concerns or Challenges: Note any concerns, challenges, or issues that were raised during the meeting, along with any proposed solutions or next steps.
                        Opportunities: Identify any potential opportunities that were discussed or hinted at during the meeting, whether for improvement, growth, or new initiatives.
                        Additional Notes: Include any other relevant information that could help in understanding the full context and outcomes of the meeting."""
    
    model = "gpt-4o"
    temperature = 0

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

    transcribed_text, prompt_tokens, completion_tokens = [response.choices[0].message.content, response.usage.prompt_tokens, response.usage.completion_tokens]


    folder_file_path = os.path.join(f"tmp_{username}", "summarized_meeting")
    local_file_path = os.path.join(folder_file_path,  output_file)

    if not os.path.exists(folder_file_path):
        os.makedirs(folder_file_path)

    # Write the text to the file
    with open(local_file_path, 'w') as file:
        file.write(transcribed_text)

    add_meeting(client_name="BlenderProducts",
                collection_name="Meetings",
                attendees=attendees)
    

    return transcribed_text


if __name__ == "__main__":
    summarize_meeting_improved("app/utils/fake_meeting.txt", "fake_meeting_summary.txt", "test")