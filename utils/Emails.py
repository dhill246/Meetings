import requests
import os
from dotenv import load_dotenv
load_dotenv()

MAILGUN_API_KEY = os.getenv('MAILGUN_API_KEY')
MAILGUN_DOMAIN = os.getenv('MAILGUN_DOMAIN')

def send_email_to_user(file_path, user="danielthill23@gmail.com"):
    try:
        api_url = "https://api.mailgun.net/v3/" + MAILGUN_DOMAIN + "/messages"

        attachment_path = "utils/TEST.txt"

        return requests.post(
            api_url,
            auth=("api", MAILGUN_API_KEY),
            files=[("attachment", open(file_path, "rb"))],
            data={"from": f"Daniel Hill <you@{MAILGUN_DOMAIN}>",
                "to": [user],
                "subject": "Hello",
                "text": "Testing some Mailgun awesomeness!"})
    
    except Exception as e:
        print(f"Failed to send email: {e}")


if __name__ == "__main__":
    send_email_to_user()