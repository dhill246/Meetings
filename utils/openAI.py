from dotenv import load_dotenv
from openai import OpenAI
import os
from pathlib import Path
import time
load_dotenv()

API_KEY = os.getenv("API_KEY")
client = OpenAI(api_key=API_KEY)

def transcribe_webm(full_path):

    with open(f"{full_path}", "rb") as audio_file:

        transcription = client.audio.transcriptions.create(
            model="whisper-1", 
            file=audio_file
        )

    body = transcription.text

    tmp, webm, user, report, date, file = full_path.split("/")

    num = file.split(".")[0]

    folder_file_path = os.path.join(f"tmp", "transcribed_chunks", user, report, date)
    local_file_path = os.path.join(folder_file_path,  f"{num}.txt")

    if not os.path.exists(folder_file_path):
        os.makedirs(folder_file_path)

    # Write the text to the file
    with open(local_file_path, 'w') as file:
        file.write(body)


def summarize_meeting(input_file, output_file):
    with open(input_file, 'r') as file:
        # Read the entire content of the file
        content = file.read()

    system_prompt = """You are a helpful assistant for the company Blender Products. 
                You will be given a one-on-one meeting. Please return the following: 
                First, give a 2-3 sentence summary of the meeting. Next, highlight any action items, 
                takeaways, and notable moments."""

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


    folder_file_path = os.path.join("tmp", "summarized_meeting")
    local_file_path = os.path.join(folder_file_path,  output_file)

    if not os.path.exists(folder_file_path):
        os.makedirs(folder_file_path)

    # Write the text to the file
    with open(local_file_path, 'w') as file:
        file.write(transcribed_text)