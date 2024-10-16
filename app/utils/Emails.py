import requests
import os
from dotenv import load_dotenv
load_dotenv()
import logging

MAILGUN_API_KEY = os.getenv('MAILGUN_API_KEY')
MAILGUN_DOMAIN = os.getenv('MAILGUN_DOMAIN')

def send_email_to_user(file_path, title, email="danielthill23@gmail.com"):
    try:
        api_url = "https://api.mailgun.net/v3/" + MAILGUN_DOMAIN + "/messages"

        return requests.post(
            api_url,
            auth=("api", MAILGUN_API_KEY),
            files=[("attachment", open(file_path, "rb"))],
            data={"from": f"Daniel Hill <daniel@{MAILGUN_DOMAIN}>",
                "to": [email],
                "subject": title,
                "text": f"Here is your meeting. Please review and let me know if you have any issues."})
    
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
                "text": f"A meeting called {title} failed to process."})
    

def send_invite_email(email, token, org_name):
    logging.info(f"Sending invite email to {email} for {org_name}")
    try:

        api_url = "https://api.mailgun.net/v3/" + MAILGUN_DOMAIN + "/messages"
        signup_url = f"meet.morphdatastrategies.com/auth/usersignup?token={token}"

        return requests.post(
                api_url,
                auth=("api", MAILGUN_API_KEY),
                data={
                    "from": f"Daniel Hill <daniel@{MAILGUN_DOMAIN}>",
                    "to": [email],
                    "subject": f"Meeting Invite for {org_name}",
                    "text": f"You've been invited to join {org_name}. Please sign up using the following link: {signup_url}. This link will expire in 7 days."
                }
            )
        
    except Exception as e:
        logging.error(f"Failed to send invite to {email}. Token: {token}. Error: {e}")
        return requests.post(
            api_url,
            auth=("api", MAILGUN_API_KEY),
            data={
                "from": f"Daniel Hill <daniel@{MAILGUN_DOMAIN}>",
                "to": ["danielthill23@gmail.com"],  # Fallback email
                "subject": "Failed to Send Invite",
                "text": f"Failed to send invite to {email}. Token: {token}. Error: {e}"
            }
        )
    
def get_subscriber_email(email):
    logging.info(f"Getting email {email}")
    try:

        api_url = "https://api.mailgun.net/v3/" + MAILGUN_DOMAIN + "/messages"
        signup_url = f"meet.morphdatastrategies.com/auth/usersignup?token={token}"

        return requests.post(
                api_url,
                auth=("api", MAILGUN_API_KEY),
                data={
                    "from": f"Daniel Hill <daniel@{MAILGUN_DOMAIN}>",
                    "to": "danielthill23@gmail.com",
                    "subject": f"You got a subscriber!!!",
                    "text": f"Someone just filled out the lead form: {email}"
                }
            )
        
    except Exception as e:
        logging.error(f"Failed to send notification to Daniel about {email}")
        return requests.post(
            api_url,
            auth=("api", MAILGUN_API_KEY),
            data={
                "from": f"Daniel Hill <daniel@{MAILGUN_DOMAIN}>",
                "to": ["danielthill23@gmail.com"],  # Fallback email
                "subject": "Failed to Send Invite",
                "text": f"Failed to send invite to {email}. Token: {token}. Error: {e}"
            }
        )




if __name__ == "__main__":
    send_email_to_user("app/utils/Steve Hill DaveDorste 07-10-2024_summary.docx")