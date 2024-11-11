from flask import render_template, jsonify, redirect, url_for, request
from flask_login import login_user, logout_user
from ..models import Organization, User, db, Invites, Free_Access_Invites
from werkzeug.security import generate_password_hash
import logging
from . import auth
import os
from ..utils.mongo import mongo_org_setup
from datetime import datetime
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
        logging.info(existing_user.password_hash)
        if existing_user.password_hash is None:
            existing_user.password_hash = generate_password_hash(password)
            # Commit the changes to the database
            db.session.commit()

            logging.info(f"User with email {existing_user.email} has set their password.")

            access_token = create_access_token(identity={"org_id": existing_user.organization_id,
                                                "user_id": existing_user.id,
                                                "role": existing_user.role})
            return jsonify({
                "message": "Existing user successfully set password",
                "access_token": access_token,
                "next_step": "home"
            }), 201

        else:

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


@auth.route("/api/first_time_signup", methods=["POST"])
def first_time_signup():

    # Ensure the request is JSON
    if not request.is_json:
        return jsonify({"error": "Invalid content type. Must be JSON."}), 400
    
    token = request.args.get("token")
    data = request.json
    email = data.get("email")
    first_name = data.get("first_name")
    last_name = data.get("last_name")
    org_name = data.get("org_name")
    cleaned_org_name = org_name.replace(" ", "")
    password = data.get("password")
    confirm_password = data.get("confirm_password")

    if token:
        plan = "solo"
        payment_status = True
    
        invite = Free_Access_Invites.query.filter_by(token=token).first()
        access_email = invite.email
    
        if not invite:
            return jsonify({"error": "Invalid or expired invite token."}), 400
        
        if email != access_email:
            return jsonify({"error": "If you'd like to use this email, please contact support or use the email the invite link was sent to."}), 400

    else:
        plan = data.get("plan")
        payment_status = False

    # Make sure all fields have been submitted
    if not email or not password or not confirm_password or not first_name or not last_name or not org_name:
        return jsonify({"error": "Please make sure all fields are filled out."}), 400
    
    # Make sure passwords match
    if password != confirm_password:
        return jsonify({"error": "Passwords do not match. Please try again."}), 400
    # Query user table by email to find out if the user already
    # has an account
    existing_user = User.query.filter_by(email=email).first()

    # Create new user if they don't exist
    if existing_user:
        logging.info(existing_user.password_hash)
        if existing_user.password_hash is None:
            existing_user.password_hash = generate_password_hash(password)
            # Commit the changes to the database
            db.session.commit()

            logging.info(f"User with email {existing_user.email} has set their password.")

            access_token = create_access_token(identity={"org_id": existing_user.organization_id,
                                                "user_id": existing_user.id,
                                                "role": existing_user.role})
            return jsonify({
                "message": "Existing user successfully set password",
                "access_token": access_token,
                "next_step": "home"
            }), 201

        else:

            logging.info(f"User with email {email} already exists.")

            return jsonify({"error": "User exists. Please log in."}), 409

    
    logging.info(f"Creating new user with email {email}.")

    # Configure a new organization setup
    new_organization = Organization(name=cleaned_org_name,
                                    plan=plan,
                                    payment_status=payment_status)
    
    db.session.add(new_organization)
    db.session.commit()

    organization_id = new_organization.id

    # Create mongodb database

    try:

        create_mongo = mongo_org_setup(cleaned_org_name, organization_id)

    except Exception as e:
        print(e)


    # Create a new user and add them to the database
    new_user = User(email=email, 
                    password_hash=generate_password_hash(password),
                    first_name=first_name,
                    last_name=last_name,
                    organization_id=organization_id,
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

@auth.route('/api/verify-free-token', methods=["GET"])
def verify_free_token():
    token = request.args.get('token')

    if not token:
        return jsonify({"valid": False, "error": "No token provided"}), 400
    
     # Query the Invites table for the token
    invite = Free_Access_Invites.query.filter_by(token=token).first()

    if not invite:
        return jsonify({"valid": False, "error": "Invalid or expired token"}), 400

    # You can also add token expiration logic here if you want, for example:
    # Check if the token is older than a certain number of hours/days
    if (datetime.now() - invite.date).days > 7:  # Assuming tokens expire after 7 days
        return jsonify({"valid": False, "error": "Token has expired"}), 400

    # If valid, return the email associated with the invite
    email = invite.email
    return jsonify({"valid": True, "email": email}), 200

# Fake addition