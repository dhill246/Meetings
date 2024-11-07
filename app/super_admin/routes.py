from . import super_admin
from flask import jsonify, request
from flask_jwt_extended import jwt_required, verify_jwt_in_request
from ..models import Organization, User, db, Free_Access_Invites, Reports
from sqlalchemy.orm import aliased
from ..utils.mongo import get_meetings_last_month, duration_to_seconds
from ..utils.Emails import send_invite_email, send_free_access_email
from ..utils.openAI import generate_ai_reply
import secrets
from datetime import datetime
from ..utils.openAI import generate_ai_reply_for_meeting
import logging
import os
from bson import ObjectId
from ..utils.mongo import get_all_manager_meetings, get_one_on_ones, get_all_employee_meetings, fetch_prompts, update_prompts, add_new_meeting_type, delete_prompts, get_recent_meetings, delete_meeting

SUPER_USER_NAME = os.getenv("SUPER_USER_NAME")
SUPER_USER_PASSWORD = os.getenv("SUPER_USER_PASSWORD")
SUPER_USER_SECRET_KEY = os.getenv("SUPER_USER_SECRET_KEY")

@super_admin.route('/send_free_invite', methods=["POST"])
def send_invite():
    logging.info("Sending invite")

    data = request.get_json()
    super_admin_username = data.get("super_admin_username")
    super_admin_password = data.get("super_admin_password")
    super_admin_secret_key = data.get("super_admin_secret_key")
    email = data.get("email")

    if (super_admin_username != SUPER_USER_NAME) or (super_admin_password != SUPER_USER_PASSWORD) or (super_admin_secret_key != SUPER_USER_SECRET_KEY):
        return jsonify({"error": "Incorrect authentication"}), 400

    # Generate token for the invite
    token = secrets.token_urlsafe(16)
    print("token:", token)


    logging.info("Adding invite to database")
     # Add the existing user as a direct report
    new_invite = Free_Access_Invites(email=email, token=token, date=datetime.now())
    db.session.add(new_invite)
    db.session.commit()

    logging.info("Sending invite email")
    send_free_access_email(email, token)

    return jsonify({"message": "Invite sent successfully"}), 200
