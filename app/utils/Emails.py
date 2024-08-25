import requests
import os
from dotenv import load_dotenv
load_dotenv()

MAILGUN_API_KEY = os.getenv('MAILGUN_API_KEY')
MAILGUN_DOMAIN = os.getenv('MAILGUN_DOMAIN')

def send_email_to_user(file_path, user, report, date, email="danielthill23@gmail.com"):
    try:
        api_url = "https://api.mailgun.net/v3/" + MAILGUN_DOMAIN + "/messages"

        return requests.post(
            api_url,
            auth=("api", MAILGUN_API_KEY),
            files=[("attachment", open(file_path, "rb"))],
            data={"from": f"Daniel Hill <daniel@{MAILGUN_DOMAIN}>",
                "to": [email],
                "subject": f"{user} meeting with {report} from {date}",
                "text": f"Here is the summary of your meeting from {date} with {report}."})
    
    except Exception as e:
        print(f"Failed to send email: {e}")

        api_url = "https://api.mailgun.net/v3/" + MAILGUN_DOMAIN + "/messages"

        return requests.post(
            api_url,
            auth=("api", MAILGUN_API_KEY),
            files=[("attachment", open(file_path, "rb"))],
            data={"from": f"Daniel Hill <daniel@{MAILGUN_DOMAIN}>",
                "to": ["danielthill23@gmail.com"],
                "subject": "FAILED MEETING",
                "text": f"A meeting with {user} and {report} failed to process."})


if __name__ == "__main__":
    send_email_to_user("app/utils/Steve Hill DaveDorste 07-10-2024_summary.docx")