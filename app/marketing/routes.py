from flask import render_template, jsonify, redirect, url_for, request, session
from ..models import Subscribers, db
from . import marketing
from ..utils.Emails import get_subscriber_email
import re

def is_valid_email(email: str) -> bool:
    """
    Validate the email format using regex.
    Returns True if valid, False otherwise.
    """
    email_regex = r"(^[\w\.\-]+@[\w\-]+\.[a-zA-Z]{2,}$)"
    return re.match(email_regex, email) is not None

@marketing.route('/api/subscribe', methods=["GET", "POST"])
def home():
    data = request.get_json()
    
    if not data or 'email' not in data:
        return jsonify({"message": "Email is required."}), 400
    
    email = data.get('email').strip().lower()
    
    # Basic email format validation
    if not is_valid_email(email):
        return jsonify({"message": "Invalid email format."}), 400
    
    # Check if email already exists
    existing_subscriber = Subscribers.query.filter_by(email=email).first()
    if existing_subscriber:
        return jsonify({"message": "Email is already subscribed."}), 409  # Conflict
    
    # Add new subscriber
    try:
        new_subscriber = Subscribers(email=email)
        db.session.add(new_subscriber)
        db.session.commit()
        get_subscriber_email(email)
        return jsonify({"message": "Subscription successful."}), 201  # Created
    except Exception as e:
        db.session.rollback()
        # Log the exception as needed
        return jsonify({"message": "An error occurred while processing your request."}), 500
