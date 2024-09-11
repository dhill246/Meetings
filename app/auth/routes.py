from flask import render_template, jsonify, redirect, url_for, request
from flask_login import login_user, logout_user
from ..models import Organization, User, db, Invites
from werkzeug.security import generate_password_hash
import logging
from . import auth
import os
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, verify_jwt_in_request

TRUSTED_DOMAIN = os.getenv("TRUSTED_DOMAIN")

@auth.route('/api/org', methods=['POST'])
def org():

    data = request.json
    org_name = data.get('org_name')
    password = data.get('password')
    logging.info(f"Email received: {org_name}")

    logging.info(f"Received attempted login from {org_name}. Looking them up.")
    organization = Organization.query.filter_by(name=org_name).first()

    if organization and organization.check_password(password):
        logging.info("Found them.")
        access_token = create_access_token(identity={"org_id": organization.id,
                                                     "user_id": None,
                                                     "role": "default"})
        logging.info(f"\nUser from {org_name} logged in.")

        # return redirect(url_for('auth.signup'))
        return jsonify({
            "message": "Organization logged in",
            "access_token": access_token,
            "next_step": "signup"
        }), 200

    
    else:
        return jsonify({"error": "Invalid credentials"}), 401


@auth.route("/api/login", methods=["POST"])
def login():
    """"
    POST request:

        - Receives: {
                        "email": "danielthill23@example.com",
                        "password": "examplepassword"
                    }

        - Returns: {
                        "access_token": "token_example",
                        "message": "User logged in",
                        "next_step": "home"
                    }
    """

    data = request.json
    email = data.get("email")
    password = data.get("password")

    user = User.query.filter_by(email=email).first()

    # If user exists, and passwords match
    if user and user.check_password(password):
        # Put user into the session
        access_token = create_access_token(identity={"org_id": user.organization_id,
                                                "user_id": user.id,
                                                "role": user.role})
        return jsonify({
            "message": "User logged in", 
            "access_token": access_token,
            "next_step": "home"
        }), 200
    
    else:
        return jsonify({"error": "Incorrect email or password"}), 401


@auth.route("/api/signup", methods=["POST"])
def signup():
    token = request.args.get("token")

    if not token:
        return jsonify({"error": "Missing token."}), 400
    
    invite = Invites.query.filter_by(token=token).first()
    
    if not invite:
        return jsonify({"error": "Invalid or expired invite token."}), 400
    
    org_id = invite.organization_id  # Assuming the Invite model has an org_id field

      # Ensure the request is JSON
    if not request.is_json:
        return jsonify({"error": "Invalid content type. Must be JSON."}), 400

    data = request.json
    first_name = data.get("first_name")
    last_name = data.get("last_name")
    email = data.get("email")
    password = data.get("password")
    confirm_password = data.get("confirm_password")

    # Make sure all fields have been submitted
    if not email or not password or not confirm_password or not first_name or not last_name:
        return jsonify({"error": "Please make sure all fields are filled out."}), 400
    
    # Make sure passwords match
    if password != confirm_password:
        return jsonify({"error": "Passwords do not match. Please try again."}), 400
    # Query user table by email to find out if the user already
    # has an account

    existing_user = User.query.filter_by(email=email).first()

    # Create new user if they don't exist
    if existing_user:
        logging.info(f"User with email {email} already exists.")

        return jsonify({"error": "User exists. Please log in."}), 409

    
    logging.info(f"Creating new user with email {email}.")

    # Create a new user and add them to the database
    new_user = User(email=email, 
                    password_hash=generate_password_hash(password),
                    first_name=first_name,
                    last_name=last_name,
                    organization_id=org_id,
                    role="default")
    
    db.session.add(new_user)
    db.session.commit()

    logging.info(f"New user created with email {email} and id {new_user.id}.")

    access_token = create_access_token(identity={"org_id": new_user.organization_id,
                                                "user_id": new_user.id,
                                                "role": new_user.role})
    return jsonify({
        "message": "User signed up",
        "access_token": access_token,
        "next_step": "home"
    }), 201
    

@auth.route('/api/logout', methods=["POST"])
def logout():
    return jsonify({"message": "User logged out", "next_step": "login"}), 200


@auth.route('/api/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    current_user = get_jwt_identity()
    new_access_token = create_access_token(identity=current_user)
    return jsonify(access_token=new_access_token)