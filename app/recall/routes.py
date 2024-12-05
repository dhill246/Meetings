from . import recall
from ..tasks import process_recall_video
from flask import render_template, jsonify, session, redirect, url_for, request, session
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
from ..models import User, Reports, db, Organization, BotRecord
import os
import secrets
import requests
from datetime import datetime
from urllib.parse import urlencode, urlunparse
import logging
from svix.webhooks import Webhook, WebhookVerificationError
from flask import Response
import json
import base64

# Zoom App Configuration
ZOOM_CLIENT_ID = os.getenv("ZOOM_CLIENT_ID")
ZOOM_REDIRECT_URI = os.getenv("ZOOM_REDIRECT_URI")
ZOOM_AUTH_BASE_URL = "https://zoom.us/oauth/authorize"
ZOOM_TOKEN_URL = "https://zoom.us/oauth/token"
RECALL_API_KEY = os.getenv("RECALL_API_KEY")
RECALL_ZOOM_OAUTH_APP_ID = os.getenv("RECALL_ZOOM_OAUTH_APP_ID")
REROUTE = os.getenv("TRUSTED_DOMAIN") + "/home/record-meeting"

# Define the new route
@recall.route("/api/start-bot", methods=["POST"])
@jwt_required()
def start_meeting_bot():
    """
    Request a meeting bot to come to the meeting via Recall's API and save to db
    """

    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']

    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401
        
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404
    
    try:
        # Extract the meeting URL from the incoming request
        data = request.json
        meeting_url = data.get("meeting_url")
        meeting_name = data.get("meeting_name")
        meeting_type = data.get("meeting_type")
        join_at = data.get("join_at")

        if not meeting_url:
            return jsonify({"error": "Missing meeting URL"}), 400

        # External API URL for starting the bot
        url = "https://us-west-2.recall.ai/api/v1/bot/"

        # API key, you can store this securely in Heroku's config vars
        recall_api_key = os.getenv("RECALL_API_KEY")  # Set this in Heroku config vars

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "Authorization": recall_api_key
        }

        # Path to the JPEG file
        jpeg_file_path = "app/recall/MorphRecordingLogo.jpg"

        # Encode the image in Base64
        with open(jpeg_file_path, "rb") as image_file:
            # Read the binary content of the image
            binary_data = image_file.read()
            # Encode to Base64
            base64_data = base64.b64encode(binary_data).decode("utf-8")


        # Bot configuration to be sent to the external API
        payload = {
            "meeting_url": meeting_url,
            "bot_name": "Morph Bot",
            "recording_mode": "audio_only",
            "join_at": join_at,
            "automatic_video_output": 
                {"in_call_recording": {
                    "kind": "jpeg",
                    "b64_data": base64_data
                }}
        }

        # Make the POST request to the external API
        response = requests.post(url, json=payload, headers=headers)
        response_data = response.json()

    except Exception as e:
        print(e)
        return jsonify({"error": str(e)}), 500

    # Check if the request was successful
    if response.status_code == 200 or response.status_code == 201:
        bot_id = response_data.get("id")
        logging.info(f"Bot with id {bot_id} has been successfully created.")
        print(f"Bot with id {bot_id} has been successfully created.")

        # Store the bot_id, meeting_url, user_id, org_id, etc. in the database or Redis for later use
        new_bot_record = BotRecord(
            bot_id=bot_id,
            user_id=user_id,
            meeting_url=meeting_url,
            meeting_name=meeting_name,
            meeting_type=meeting_type,
            status="pending",
            status_time=datetime.now(),  # Initialize with current time
            sub_code=None,              # Can be updated later by webhook
            message=None,               # Can be updated later by webhook
            recording_id=None,          # Can be updated later by webhook
            org_id=org_id,
        )

        print(f"Bot initialized for loading to db with id {bot_id}")

        db.session.add(new_bot_record)
        db.session.commit()

        return jsonify({"status": "Bot started successfully. Please give the bot up to 30 seconds to join your meeting.", "data": response_data}), 200

    else:
        print(f"Failed to start bot: {response_data}.")
        return jsonify({"status": "Failed to start bot", "data": response_data}), response.status_code
    
@recall.route("/api/webhook", methods=["POST"])
def webhook():
    """
    Listener to receive updates from Recall meeting bot and calendar events.
    """
    print("Received webhook request")
    
    headers = request.headers
    print(f"Headers received: {headers}")

    payload = request.get_data()
    print(f"Payload received: {payload}")

    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
    print("Retrieved webhook secret")

    try:
        # Verify the webhook using the secret key
        wh = Webhook(WEBHOOK_SECRET)
        print("Webhook object created")

        wh.verify(payload, headers)
        print("Webhook verified")

        # Extract the JSON payload from the incoming request
        data = request.json
        print(f"Extracted data from payload: {data}")

        # Check what event was triggered
        event = data.get("event")
        print(f"Event type: {event}")
        
        if event == "bot.status_change":
            print("Processing bot.status_change event")
            
            # Handle bot status change event
            bot_id = data["data"]["bot_id"]
            print(f"Extracted bot_id: {bot_id}")

            status_info = data["data"]["status"]
            print(f"Extracted status_info: {status_info}")

            status_code = status_info.get("code")
            print(f"Extracted status_code: {status_code}")

            status_time = status_info.get("created_at")
            print(f"Extracted status_time: {status_time}")

            sub_code = status_info.get("sub_code")
            print(f"Extracted sub_code: {sub_code}")

            message = status_info.get("message")
            print(f"Extracted message: {message}")

            recording_id = status_info.get("recording_id")  # May be absent
            print(f"Extracted recording_id: {recording_id}")

            # Retrieve the bot record from the database
            bot_record = BotRecord.query.filter_by(bot_id=bot_id).first()
            print(f"Bot record found: {bot_record}")

            if not bot_record:
                logging.error(f"Bot record not found for bot_id {bot_id}")
                return jsonify({"error": "Bot record not found for bot_id"}), 404
            print("Bot record found successfully")

            # Update the bot_record with the new status
            bot_record.status = status_code
            print("Updated bot_record status")

            bot_record.status_time = status_time
            print("Updated bot_record status_time")

            bot_record.sub_code = sub_code
            print("Updated bot_record sub_code")

            bot_record.message = message
            print("Updated bot_record message")

            bot_record.recording_id = recording_id  # Ensure this field exists in your model
            print("Updated bot_record recording_id")

            db.session.commit()
            print("Database commit successful")

            # Perform actions based on status_code
            if status_code == "done":
                print("Status is 'done', calling retrieve_bot function")
                retrieve_bot(bot_id)
            print("Completed status handling")
        
        elif event == "calendar.update":
            print("Processing calendar.update event")
            calendar_id = data["data"]["calendar_id"]
            print(f"Extracted calendar_id: {calendar_id}")
            
            # Re-fetch the calendar to get the latest state
            # Implement your logic to handle calendar updates here
            # Example: update_calendar_state(calendar_id)

        elif event == "calendar.sync_events":
            print("Processing calendar.sync_events event")
            calendar_id = data["data"]["calendar_id"]
            last_updated_ts = data["data"]["last_updated_ts"]
            print(f"Extracted calendar_id: {calendar_id}, last_updated_ts: {last_updated_ts}")
            
            # Re-fetch the calendar events for this calendar
            # Implement your logic to sync calendar events here
            # Example: sync_calendar_events(calendar_id, last_updated_ts)

        else:
            logging.warning(f"Unhandled event type: {event}")
        
        # Return a success response to acknowledge receipt
        print("Webhook processed successfully, returning success response")
        return jsonify({"status": "success"}), 200

    except Exception as e:
        logging.error(f"Error processing webhook: {e}")
        return jsonify({"error": str(e)}), 500


def retrieve_bot(bot_id):
    """
    Function to be called after bot status is done. This retrieves the url 
    from Recall API and starts the background worker job to process.
    """

    try:
        # API key, securely stored in environment variables
        api_key = os.getenv("RECALL_API_KEY")  # Ensure this is set in your environment

        headers = {
            "accept": "application/json",
            "Authorization": api_key
        }

        # API URL to retrieve bot details
        url = f"https://us-west-2.recall.ai/api/v1/bot/{bot_id}"

        # Make the GET request to retrieve bot data
        response = requests.get(url, headers=headers)
        response_data = response.json()

        # Check if the request was successful
        if response.status_code == 200:
            # Retrieve the bot record from the database
            bot_record = BotRecord.query.filter_by(bot_id=bot_id).first()
            if not bot_record:
                logging.error(f"Bot record not found for bot_id {bot_id}")
                return

            # Check if 'video_url' is present in the response data
            video_url = response_data.get("video_url")
            
            if video_url:

                video_filename = f"{bot_id}.mp4"

                video_filepath = os.path.join("videos", video_filename)  # Ensure 'videos' directory exists

                # Update the bot_record with the video file path
                bot_record.video_file_path = video_filepath

                user_id = bot_record.user_id
                org_id = bot_record.org_id
                meeting_type = bot_record.meeting_type

                db.session.commit()

                user = User.query.filter_by(id=user_id).first()
                org = Organization.query.filter_by(id=org_id).first()


                attendees_info = {
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "email": user.email,
                    "user_id": user.id,
                    "role": "Manager"
                }

                org_info = {"name": org.name,
                            "org_id": org.id}

                # Call the Celery task to process the video
                process_recall_video.delay(
                    video_filepath=video_filepath,
                    bot_id=bot_id,
                    video_url=video_url,
                    meeting_type=meeting_type,
                    user=attendees_info,
                    org=org_info,
                    meeting_name=bot_record.meeting_name
                )

            else:
                logging.warning(f"No video_url available for bot {bot_id} at this time.")

        else:
            logging.error(f"Failed to retrieve bot {bot_id}. Response: {response_data}")

    except Exception as e:
        logging.error(f"Error retrieving bot {bot_id}: {e}")

def generate_auth_url(redirect_uri, client_id):
    base_url = "https://zoom.us/oauth/authorize"
    query_params = {
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "client_id": client_id,
    }
    return base_url + "?" + urlencode(query_params)

@recall.route("/api/connect-zoom", methods=["GET"])
def connect_zoom():

    # Construct the Zoom OAuth URL
    auth_url = generate_auth_url(ZOOM_REDIRECT_URI, ZOOM_CLIENT_ID)

    # Return the URL to the frontend
    return jsonify({"auth_url": auth_url}), 200

def create_creds(authorization_code):
    # Call the Recall API to create Zoom OAuth Credential
    recall_api_url = "https://us-west-2.recall.ai/api/v2/zoom-oauth-credentials/"
    headers = {
        "Authorization": RECALL_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "oauth_app": RECALL_ZOOM_OAUTH_APP_ID,
        "authorization_code": {
            "code": authorization_code,
            "redirect_uri": ZOOM_REDIRECT_URI,
        },
    }

    response = requests.post(recall_api_url, json=payload, headers=headers)
    details = response.json()

    return response, details


@recall.route("/api/oauth-callback/zoom")
def zoom_oauth_callback():
    # Extract the authorization code from the callback URL
    authorization_code = request.args.get("code")
    if not authorization_code:
        return Response(f"""
            <html>
                <body style="text-align: center; margin-top: 20px; font-family: Arial, sans-serif;">
                    <h1>Authorization failed. No code provided.</h1>
                    <p>Redirecting you back to Morph Meetings in 5 seconds.</p>
                    <script>
                        setTimeout(function() {{
                            window.location.href = "{REROUTE}";
                        }}, 5000);
                    </script>
                </body>
            </html>
        """, mimetype="text/html")
    
    response, details = create_creds(authorization_code)

    if response.status_code == 201:
        return Response(f"""
            <html>
                <body style="text-align: center; margin-top: 20px; font-family: Arial, sans-serif;">
                    <h1>Zoom account successfully connected!</h1>
                    <p>Redirecting you back to Morph Meetings in 5 seconds.</p>
                    <script>
                        setTimeout(function() {{
                            window.location.href = "{REROUTE}";
                        }}, 5000);
                    </script>
                </body>
            </html>
        """, mimetype="text/html")
    elif response.status_code == 400 and "Zoom OAuth Credential already exists" in details.get("detail", ""):
            
            conflicting_zoom_account_id = details.get("conflicting_zoom_account_id")


            url = f"https://us-west-2.recall.ai/api/v2/zoom-oauth-credentials/{conflicting_zoom_account_id}/"

            headers = {"Authorization": RECALL_API_KEY}

            response = requests.delete(url, headers=headers)

            response, details = create_creds(authorization_code)
        
            # Custom message for already integrated Zoom account
            return Response(f"""
                <html>
                    <body style="text-align: center; margin-top: 20px; font-family: Arial, sans-serif;">
                        <h1>Your Zoom account has already been integrated. We deleted your integration and successfully reauthorized.</h1>
                        <p>Redirecting you back to Morph Meetings in 5 seconds.</p>
                        <script>
                            setTimeout(function() {{
                                window.location.href = "{REROUTE}";
                            }}, 5000);
                        </script>
                    </body>
                </html>
            """, mimetype="text/html")
    else:
        message = details.get("detail", "Error creating Zoom OAuth Credential.")
        return Response(f"""
            <html>
                <body style="text-align: center; margin-top: 20px; font-family: Arial, sans-serif;">
                    <h1>Failed to Connect Zoom Account</h1>
                    <p>{message}</p>
                    <p>{details}</p>
                    <p>Redirecting you back to Morph Meetings in 5 seconds.</p>
                    <script>
                        setTimeout(function() {{
                            window.location.href = "{REROUTE}";
                        }}, 5000);
                    </script>
                </body>
            </html>
        """, mimetype="text/html")
        
def fetch_tokens_from_authorization_code_for_microsoft_outlook(code):
    """Fetch OAuth tokens from Microsoft using an authorization code."""
    token_endpoint = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    
    # Update the payload to match Microsoft's requirements
    payload = {
        "client_id": os.getenv("MICROSOFT_OUTLOOK_OAUTH_CLIENT_ID"),
        "client_secret": os.getenv("MICROSOFT_OUTLOOK_OAUTH_CLIENT_SECRET"),
        "redirect_uri": f"{os.getenv('PUBLIC_URL')}/oauth-callback/microsoft-outlook",
        "grant_type": "authorization_code",
        "code": code,
        "scope": "offline_access openid email https://graph.microsoft.com/Calendars.Read"
    }
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
    }
    
    try:
        response = requests.post(token_endpoint, data=payload, headers=headers)
        # Add debug logging
        print(f"Token exchange response: {response.status_code}")
        print(f"Response content: {response.text}")
        
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Token exchange error: {str(e)}")
        print(f"Response content: {e.response.text if hasattr(e, 'response') else 'No response content'}")
        raise

def build_microsoft_outlook_oauth_url(state):
    """Build the Microsoft OAuth URL for authorization."""
    oauth_endpoint = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    params = {
        "client_id": os.getenv("MICROSOFT_OUTLOOK_OAUTH_CLIENT_ID"),
        "redirect_uri": f"{os.getenv("PUBLIC_URL")}/oauth-callback/microsoft-outlook",
        "response_type": "code",
        "scope": "offline_access openid email https://graph.microsoft.com/Calendars.Read",
        "state": json.dumps(state),
    }
    query_string = urlencode(params)
    return f"{oauth_endpoint}?{query_string}"

@recall.route("/oauth-callback/microsoft-outlook", methods=["GET"])
def microsoft_outlook_oauth_callback():
    """Handle the OAuth callback from Microsoft."""
    try:
        # Retrieve and validate state
        returned_state = request.args.get("state")
        if not returned_state:
            return Response(f"""
                <html>
                    <body style="text-align: center; margin-top: 20px; font-family: Arial, sans-serif;">
                        <h1>State parameter is missing.</h1>
                        <p>Redirecting you back to Morph Meetings in 5 seconds.</p>
                        <script>
                            setTimeout(function() {{
                                window.location.href = "{REROUTE}";
                            }}, 5000);
                        </script>
                    </body>
                </html>
            """, mimetype="text/html"), 400

        try:
            state = json.loads(returned_state)
        except json.JSONDecodeError:
            return Response(f"""
                <html>
                    <body style="text-align: center; margin-top: 20px; font-family: Arial, sans-serif;">
                        <h1>Invalid state parameter.</h1>
                        <p>Redirecting you back to Morph Meetings in 5 seconds.</p>
                        <script>
                            setTimeout(function() {{
                                window.location.href = "{REROUTE}";
                            }}, 5000);
                        </script>
                    </body>
                </html>
            """, mimetype="text/html"), 400

        # Extract authorization code and user details
        code = request.args.get("code")
        
        if not code:
            return Response(f"""
                <html>
                    <body style="text-align: center; margin-top: 20px; font-family: Arial, sans-serif;">
                        <h1>Authorization code is missing.</h1>
                        <p>Redirecting you back to Morph Meetings in 5 seconds.</p>
                        <script>
                            setTimeout(function() {{
                                window.location.href = "{REROUTE}";
                            }}, 5000);
                        </script>
                    </body>
                </html>
            """, mimetype="text/html"), 400

        # Fetch OAuth tokens
        oauth_tokens = fetch_tokens_from_authorization_code_for_microsoft_outlook(code)

        if "error" in oauth_tokens:
            return Response(f"""
                <html>
                    <body style="text-align: center; margin-top: 20px; font-family: Arial, sans-serif;">
                        <h1>Failed to exchange code for tokens</h1>
                        <p>{oauth_tokens.get("error_description", "No description provided")}</p>
                        <p>Redirecting you back to Morph Meetings in 5 seconds.</p>
                        <script>
                            setTimeout(function() {{
                                window.location.href = "{REROUTE}";
                            }}, 5000);
                        </script>
                    </body>
                </html>
            """, mimetype="text/html"), 400

        # Call create calendar in Recall
        url = "https://us-west-2.recall.ai/api/v2/calendars/"

        payload = {
            "platform": "microsoft_outlook",
            "oauth_client_id": os.getenv("MICROSOFT_OUTLOOK_OAUTH_CLIENT_ID"),
            "oauth_client_secret": os.getenv("MICROSOFT_OUTLOOK_OAUTH_CLIENT_SECRET"),
            "oauth_refresh_token": oauth_tokens.get("refresh_token") 
        }

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "Authorization": os.getenv("RECALL_API_KEY")
        }

        response = requests.post(url, json=payload, headers=headers)

        if response.status_code == 201:
            return Response(f"""
                <html>
                    <body style="text-align: center; margin-top: 20px; font-family: Arial, sans-serif;">
                        <h1>Successfully connected Microsoft calendar!</h1>
                        <p>Redirecting you back to Morph Meetings in 5 seconds.</p>
                        <script>
                            setTimeout(function() {{
                                window.location.href = "{REROUTE}";
                            }}, 5000);
                        </script>
                    </body>
                </html>
            """, mimetype="text/html"), 201

        else:
            return Response(f"""
                <html>
                    <body style="text-align: center; margin-top: 20px; font-family: Arial, sans-serif;">
                        <h1>Unexpected error</h1>
                        <p>Status code: {response.status_code}</p>
                        <p>Details: {response.text}</p>
                        <p>Redirecting you back to Morph Meetings in 5 seconds.</p>
                        <script>
                            setTimeout(function() {{
                                window.location.href = "{REROUTE}";
                            }}, 5000);
                        </script>
                    </body>
                </html>
            """, mimetype="text/html"), response.status_code

    except requests.exceptions.RequestException as e:
        return Response(f"""
            <html>
                <body style="text-align: center; margin-top: 20px; font-family: Arial, sans-serif;">
                    <h1>Token exchange failed</h1>
                    <p>Details: {str(e)}</p>
                    <p>Redirecting you back to Morph Meetings in 5 seconds.</p>
                    <script>
                        setTimeout(function() {{
                            window.location.href = "{REROUTE}";
                        }}, 5000);
                    </script>
                </body>
            </html>
        """, mimetype="text/html"), 500
    except Exception as e:
        return Response(f"""
            <html>
                <body style="text-align: center; margin-top: 20px; font-family: Arial, sans-serif;">
                    <h1>Internal server error</h1>
                    <p>Details: {str(e)}</p>
                    <p>Redirecting you back to Morph Meetings in 5 seconds.</p>
                    <script>
                        setTimeout(function() {{
                            window.location.href = "{REROUTE}";
                        }}, 5000);
                    </script>
                </body>
            </html>
        """, mimetype="text/html"), 500

    
@recall.route("/api/connect-outlook", methods=["GET"])
def connect_outlook():
    
    # Generate a random state
    state = secrets.token_urlsafe(16)

    # Save the state in the session
    session["outlook_oauth_state"] = state

    # Construct the Zoom OAuth URL
    auth_url = build_microsoft_outlook_oauth_url(state)

    # Return the URL to the frontend
    return jsonify({"auth_url": auth_url}), 200