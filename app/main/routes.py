from flask import render_template, jsonify, redirect, url_for, request, session
from ..models import User, Reports, db, Organization, BotRecord
from . import main
from ..utils.s3_utils import check_existing_s3_files, read_text_file
from datetime import datetime
from flask_socketio import emit
from functools import wraps
import logging
import os
import requests
from svix.webhooks import Webhook, WebhookVerificationError
from botocore.exceptions import ClientError
from bson import ObjectId
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
from ..utils.mongo import get_meeting_by_id, fetch_meeting_types, get_general_meetings, get_oneonone_meetings, fetch_personal_prompts, fetch_prompts, add_new_meeting_type, update_prompts, delete_prompts, get_one_on_ones, update_notes
from ..utils.openAI import generate_ai_reply
from ..tasks import process_recall_video


# Utility function to convert ObjectId to string
def convert_object_id_to_str(data):
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, ObjectId):
                data[key] = str(value)
            elif isinstance(value, dict):
                data[key] = convert_object_id_to_str(value)
            elif isinstance(value, list):
                data[key] = [convert_object_id_to_str(item) for item in value]
    return data    

@main.route('/api/home', methods=["GET", "POST"])
@jwt_required()
def home():
    """
    GET request:

        - Returns: {
                        "current_user": 135,
                        "direct_reports": [
                            {
                                "first_name": "Daniel",
                                "last_name": "Hill",
                                "id": 137
                            }
                        ]
                    }


    # POST request:

    #     - Receives: {"report_id": 137}

    #     - Returns:  {
    #                     "date": "08-27-2024",
    #                     "manager_firstname": "Daniel",
    #                     "manager_lastname": "Hill",
    #                     "next_step": "record",
    #                     "report_firstname": "Daniel",
    #                     "report_id": 137,
    #                     "report_lastname": "Hill",
    #                     "user_id": 135
    #                 }
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

    direct_reports = [{"id": r.report_id, "first_name": r.report.first_name, "last_name": r.report.last_name} for r in current_user.managed_reports]

    return jsonify({"current_user": int(current_user.get_id()), "direct_reports": direct_reports}), 200

@main.route("/api/add_report", methods=["POST"])
@jwt_required()
def add_report():

    """
    POST request:

        - Receives: {
                        "first_name": "Joe",
                        "last_name": "Shmoe",
                        "email": "joe.shmoe@gmail.com"
                    }

        - Returns: {
                        "message": "Joe Shmoe has been added as a new direct report."
                    }
    """

    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']

    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    if not org_id or not user_id:
        print("Please log in to access this page.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401
    
    data = request.json
    first_name = data.get("first_name")
    last_name = data.get("last_name")
    email = data.get("email")

    if first_name == "" or last_name == "" or email == "":

        return jsonify({"error": "Please provide all required fields"}), 400
    

    # Check if the user already exists in the database
    existing_user = User.query.filter_by(first_name=first_name, 
                                         last_name=last_name,
                                         email=email).first()

    if existing_user:
        # Check if the existing user is already a direct report
        existing_report = Reports.query.filter_by(manager_id=current_user.id, report_id=existing_user.id).first()
        
        if existing_report:
            print(f"{existing_user.first_name} {existing_user.last_name} is already your direct report.")
            return jsonify({"message": f"{existing_user.first_name} {existing_user.last_name} is already your direct report."}), 200

        else:
            # Add the existing user as a direct report
            new_report = Reports(manager_id=current_user.id, report_id=existing_user.id, organization_id=current_user.organization_id)
            db.session.add(new_report)
            db.session.commit()
            print(f"{existing_user.first_name} {existing_user.last_name} has been added as your direct report.")
            return jsonify({"message": f"{existing_user.first_name} {existing_user.last_name} has been added as your direct report."}), 201

    else:
        existing_email = User.query.filter_by(email=email).first()

        if existing_email:
            return jsonify({"error": f"{email} is already in use by a report."}), 404


        # Create a new user and add them as a direct report
        new_user = User(first_name=first_name, 
                        last_name=last_name, 
                        email=email,
                        organization_id=current_user.organization_id,
                        role="default")
        
        db.session.add(new_user)
        db.session.commit()

        new_report = Reports(manager_id=current_user.id, report_id=new_user.id, organization_id=current_user.organization_id)
        db.session.add(new_report)
        db.session.commit()

    return jsonify({"message": f"{new_user.first_name} {new_user.last_name} has been added as a new direct report."}), 201

@main.route("/api/remove_report/<int:report_id>", methods=["DELETE"])
@jwt_required()
def remove_report(report_id):
    """
    DELETE request:

        - Returns: {
                        "message": "Report relationship removed."
                    }

    """

    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']

    if not org_id or not user_id:
        print("Please log in to access this page.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401
    
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404
    
    # Find the report relationship to remove
    report_relationship = Reports.query.filter_by(manager_id=current_user.id, report_id=report_id).first()

    if report_relationship:
        db.session.delete(report_relationship)
        db.session.commit()
        return jsonify({"message": "Report relationship removed."}), 200

    return jsonify({"error": "Report relationship not found."}), 404

@main.route("/api/view_meetings/oneonone/<int:report_id>", methods=["GET"])
@jwt_required()
def view_oneonone_meetings(report_id):

    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']

    if not org_id or not user_id:
        print("Please log in to access this page.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401

    report = User.query.get(report_id)

    org = Organization.query.get(org_id)

    if not report:
        return jsonify({"error": "Report not found."}), 404
    
    attendee_info = {"manager_id": user_id, "report_id": report_id}

    meetings = get_oneonone_meetings("One-on-One", org.name, org_id, attendee_info)

    meetings_list = [{"meeting_id": str(m["_id"]), 
                    "date": m["date"], 
                    "summary": m["summary"].get("Meeting Summary") or m["summary"].get("Meeting summary")} 
                    for m in meetings]
    
    return jsonify({"report": {"id": report.id, "first_name": report.first_name, "last_name": report.last_name}, "meetings": meetings_list}), 200

@main.route('/api/meeting/<string:meeting_id>', methods=["GET"])
@jwt_required()
def get_meeting(meeting_id):
    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']

    if not org_id or not user_id:
        print("Please log in to access this page.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401
        
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    org = Organization.query.get(org_id)

    meeting_info = get_meeting_by_id(org.name, org_id, meeting_id)

    if not meeting_info:
        return jsonify({"error": "Meeting not found"}), 404

    # Convert any ObjectId instances in the response to strings
    meeting_info = convert_object_id_to_str(meeting_info)

    return jsonify({"meeting": meeting_info}), 200
    
    

@main.route('/api/oneonone/<int:report_id>', methods=['GET'])
@jwt_required()
def oneonone(report_id):
    """
    GET request: 
        - Receives: {
                        "report_id": 139
                    }

        - Returns: {
                        "next_step": "record",
                        "user_id": user.id,
                        "report_id": report_id,
                        "manager_firstname": user.first_name,
                        "manager_lastname": user.last_name,
                        "report_firstname": report.first_name,
                        "report_lastname": report.last_name,
                        "date": date
                    }
    """

    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']

    if not org_id or not user_id:
        print("Please log in to access this page.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401

    user = User.query.get(user_id)
    report = User.query.get(report_id)

    # Get the current date
    today = datetime.now()

    # Format the date as MM-DD-YYYY
    date = today.strftime("%m-%d-%Y")

    username = f"{user.first_name} {user.last_name}"
    firstname = report.first_name
    lastname = report.last_name

    list_s3 = check_existing_s3_files()
    list_s3_webm = set(["/".join(x.rsplit("/", 1)[:-1]) for x in list_s3])

    if (f"{username}/{firstname}{lastname}/{date}" in list_s3_webm) or (f"Summary_{username}_{firstname}{lastname}_{date}.txt" in list_s3):
        return jsonify({"error": "Duplicate record found."}), 409

    return  jsonify({
                "next_step": "record",
                "user_id": user.id,
                "report_id": report_id,
                "manager_firstname": user.first_name,
                "manager_lastname": user.last_name,
                "report_firstname": report.first_name,
                "report_lastname": report.last_name,
                "date": date
            }), 200


@main.route('/api/generalmeeting/<meeting_type>', methods=['GET'])
@jwt_required()
def generalmeeting(meeting_type):
    """
    GET request: 
        - Receives: {
                        "meeting_type": "Any"
                    }

        - Returns: {
                        "next_step": "record",
                        "user_id": user.id,
                        "report_id": report_id,
                        "manager_firstname": user.first_name,
                        "manager_lastname": user.last_name,
                        "report_firstname": report.first_name,
                        "report_lastname": report.last_name,
                        "date": date
                    }
    """

    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']

    if not org_id or not user_id:
        print("Please log in to access this page.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401

    user = User.query.get(user_id)

    # Get the current date
    today = datetime.now()

    # Format the date as MM-DD-YYYY
    date = today.strftime("%m-%d-%Y")

    username = f"{user.first_name} {user.last_name}"
    firstname = meeting_type
    lastname = ""

    list_s3 = check_existing_s3_files()
    list_s3_webm = set(["/".join(x.rsplit("/", 1)[:-1]) for x in list_s3])

    if (f"{username}/{firstname}{lastname}/{date}" in list_s3_webm) or (f"Summary_{username}_{firstname}{lastname}_{date}.txt" in list_s3):
        return jsonify({"error": "Duplicate record found."}), 409
    
    return  jsonify({
                "next_step": "record",
                "user_id": user.id,
                "manager_firstname": user.first_name,
                "manager_lastname": user.last_name,
                "meeting_type": meeting_type,
                "date": date
            }), 200

@main.route('/api/othermeeting/<meeting_type>', methods=['GET'])
@jwt_required()
def othermeeting(meeting_type):
    """
    GET request: 
        - Receives: {
                        "meeting_type": "Any"
                    }

        - Returns: {
                        "next_step": "record",
                        "user_id": user.id,
                        "report_id": report_id,
                        "manager_firstname": user.first_name,
                        "manager_lastname": user.last_name,
                        "report_firstname": report.first_name,
                        "report_lastname": report.last_name,
                        "date": date
                    }
    """

    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']

    if not org_id or not user_id:
        print("Please log in to access this page.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401

    user = User.query.get(user_id)

    # Get the current date
    today = datetime.now()

    # Format the date as MM-DD-YYYY
    date = today.strftime("%m-%d-%Y")

    username = f"{user.first_name} {user.last_name}"
    firstname = meeting_type
    lastname = ""

    list_s3 = check_existing_s3_files()
    list_s3_webm = set(["/".join(x.rsplit("/", 1)[:-1]) for x in list_s3])

    if (f"{username}/{firstname}{lastname}/{date}" in list_s3_webm) or (f"Summary_{username}_{firstname}{lastname}_{date}.txt" in list_s3):
        return jsonify({"error": "Duplicate record found."}), 409
    
    return  jsonify({
                "next_step": "record",
                "user_id": user.id,
                "manager_firstname": user.first_name,
                "manager_lastname": user.last_name,
                "meeting_type": meeting_type,
                "date": date
            }), 200

@main.route('/api/get_meeting_types', methods=['GET'])
@jwt_required()
def get_meeting_types():
    """
    GET request: 

        - Returns: {
                        "meeting_types": ["One-on-One", "Any"]
                    }
    """

    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']

    if not org_id or not user_id:
        print("Please log in to access this page.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401

    user = User.query.get(user_id)
    org = Organization.query.get(user.organization_id)


    meeting_types = fetch_meeting_types(org.name, org_id, scope=user_id)


    return  jsonify({
                "meeting_types": meeting_types
            }), 200

@main.route('/api/view_meetings/othermeeting/<meeting_type>', methods=['GET'])
@jwt_required()
def view_other_meeting(meeting_type):
    """
    GET request: 

        - Returns: {
                        "meeting_types": ["One-on-One", "Any"]
                    }
    """

    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']

    meeting_type = meeting_type.replace("_", " ")

    if not org_id or not user_id:
        print("Please log in to access this page.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401

    org = Organization.query.get(org_id)

    attendee_info = {"user_id": user_id,
                     "role": "Manager"}
    
    meetings = get_general_meetings(meeting_type, org.name, org_id, attendee_info)

    meetings_list = [{"meeting_id": str(m["_id"]), 
                    "date": m["date"], 
                    "summary": m["summary"].get("Meeting Summary") or m["summary"].get("Meeting summary")} 
                    for m in meetings]
    
    print(meetings_list)
    return jsonify({"meetings": meetings_list}), 200

@main.route('/api/view_meetings/generalmeeting', methods=['GET'])
@jwt_required()
def view_general_meetings():
    """
    GET request: 

        - Returns: {
                        "meeting_types": ["One-on-One", "Any"]
                    }
    """

    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']

    meeting_type = "General Meeting"

    if not org_id or not user_id:
        print("Please log in to access this page.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401

    org = Organization.query.get(org_id)

    attendee_info = {"user_id": user_id,
                     "role": "Manager"}
    
    meetings = get_general_meetings(meeting_type, org.name, org_id, attendee_info)

    meetings_list = [{"meeting_id": str(m["_id"]), 
                    "date": m["date"], 
                    "name": m.get("meeting_name") or "General Meeting", 
                    "summary": m["summary"].get("Meeting Summary") or m["summary"].get("Meeting summary")} 
                    for m in meetings]
    
    print(meetings_list)
    return jsonify({"meetings": meetings_list}), 200

@main.route('/api/fetch_prompts_manager', methods=["GET"])
@jwt_required()
def fetch_prompts_manager():
    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']
    role = claims['sub']['role']

    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 40
        
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    org = Organization.query.get(org_id)

    print("Arguments: ", org.name, org_id, role)
    prompts = fetch_personal_prompts(org_name=org.name, org_id=org_id, role=role, scope=user_id)

    print(prompts)

    if prompts == None:
        return jsonify({"error": "No prompts found"}), 404
    else:
        prompts_list = [
                {
                    "prompt_id": str(m["_id"]),
                    "default_prompts": m.get("default_prompts", {}),  # Ensure 'personal_prompts' exists
                    "type": m.get("type_name", ""),  # Ensure 'type_name' exists (though it should)
                    "description": m.get("description", "")  # Provide empty string if 'description' doesn't exist
                }
            for m in prompts
            ]

        return jsonify({"prompts": prompts_list}), 200


@main.route('/api/fetch_company_meeting_types', methods=["GET"])
@jwt_required()
def fetch_company_meeting_types():
    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']
    role = "admin"

    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401
        
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    org = Organization.query.get(org_id)

    print("Arguments: ", org.name, org_id, role)
    prompts = fetch_prompts(org.name, org_id, scope="company_wide")

    if prompts == None:
        return jsonify({"error": "No prompts found"}), 404
    else:
        prompts_list = [{"prompt_id": str(m["_id"]), "default_prompts": m["default_prompts"], "type": m["type_name"], "description": m["description"]} for m in prompts]

        return jsonify({"prompts": prompts_list}), 200
    
@main.route('/api/fetch_all_meeting_types', methods=["GET"])
@jwt_required()
def fetch_all_meeting_types():
    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']
    role = claims['sub']['role']

    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401
        
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    org = Organization.query.get(org_id)

    # Fetch company-wide meeting types
    print("Fetching company-wide prompts: ", org.name, org_id)
    company_prompts = fetch_prompts(org.name, org_id, scope="company_wide")
    if company_prompts is None:
        company_prompts = []
    else:
        company_prompts = [
            {
                "prompt_id": str(m["_id"]),
                "default_prompts": m["default_prompts"],
                "type": m["type_name"],
                "description": m["description"],
                "scope": "company_wide"
            } for m in company_prompts
        ]
    
    # Fetch personal meeting types
    print("Fetching personal prompts: ", org.name, org_id, user_id)
    personal_prompts = fetch_prompts(org.name, org_id, scope=user_id)
    if personal_prompts is None:
        personal_prompts = []
    else:
        personal_prompts = [
            {
                "prompt_id": str(m["_id"]),
                "default_prompts": m["default_prompts"],
                "type": m["type_name"],
                "description": m["description"],
                "scope": "personal"
            } for m in personal_prompts
        ]

    # Combine the two lists
    all_prompts = company_prompts + personal_prompts

    if not all_prompts:
        return jsonify({"error": "No prompts found"}), 404
    else:
        return jsonify({"prompts": all_prompts}), 200

    
@main.route('/api/add_meeting_type_manager', methods=["POST"])
@jwt_required()
def add_meeting_type_manager():
    # Extract JWT claims
    claims = verify_jwt_in_request()[1]
    org_id = claims['sub'].get('org_id')
    user_id = claims['sub'].get('user_id')
    role = claims['sub'].get('role')

    # Check for valid org_id and user_id
    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401

    # Retrieve the current user
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    # Retrieve the organization
    org = Organization.query.get(org_id)
    if not org:
        return jsonify({"error": "Organization not found"}), 404

    # Retrieve JSON data from the request
    new_meeting_type_data = request.json
    print("new_meeting_type_data:", new_meeting_type_data)

    # Validate the input data
    required_fields = ["type_name", "description", "default_prompts"]
    for field in required_fields:
        if field not in new_meeting_type_data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    # You might want to add more validation here (e.g., check data types, lengths)

    # Call the function to add the new meeting type
    try:
        add_new_meeting_type(
            org_name=org.name,
            org_id=org_id,
            role=role,
            meeting_type_data=new_meeting_type_data,
            scope="company_wide"
        )
    except Exception as e:
        print(f"Error adding new meeting type: {e}")
        return jsonify({"error": "Failed to add new meeting type"}), 500

    return jsonify({"message": "Meeting type added successfully"}), 200


@main.route('/api/add_meeting_type_personal', methods=["POST"])
@jwt_required()
def add_meeting_type_personal():
    # Extract JWT claims
    claims = verify_jwt_in_request()[1]
    org_id = claims['sub'].get('org_id')
    user_id = claims['sub'].get('user_id')
    role = claims['sub'].get('role')

    # Check for valid org_id and user_id
    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401

    # Retrieve the current user
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    # Retrieve the organization
    org = Organization.query.get(org_id)
    if not org:
        return jsonify({"error": "Organization not found"}), 404

    # Retrieve JSON data from the request
    new_meeting_type_data = request.json
    print("new_meeting_type_data:", new_meeting_type_data)

    # Validate the input data
    required_fields = ["type_name", "description", "default_prompts"]
    for field in required_fields:
        if field not in new_meeting_type_data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    # You might want to add more validation here (e.g., check data types, lengths)

    # Call the function to add the new meeting type
    try:
        add_new_meeting_type(
            org_name=org.name,
            org_id=org_id,
            role=role,
            meeting_type_data=new_meeting_type_data,
            scope=user_id
        )
    except Exception as e:
        print(f"Error adding new meeting type: {e}")
        return jsonify({"error": "Failed to add new meeting type"}), 500

    return jsonify({"message": "Meeting type added successfully"}), 200


@main.route('/api/update_personal_prompt/<prompt_id>', methods=["POST"])
@jwt_required()
def update_prompt(prompt_id):
    """
    User update an existing prompt.
    """

    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']
    role = claims['sub']['role']

    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401
        
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    org = Organization.query.get(org_id)

    # Retrieve JSON data from the request
    updated_data = request.json
    print("updated_data:", updated_data)

    update_prompts(org.name, org_id, role, prompt_id, updated_data, scope=user_id)

    return jsonify({"message": "Prompt updated successfully"}), 200

@main.route('/api/delete_prompt_manager/<prompt_id>', methods=["GET"])
@jwt_required()
def delete_prompt(prompt_id):

    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']
    role = claims['sub']['role']

    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401
        
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    org = Organization.query.get(org_id)

    print("Deleting prompt with arguments: ", org.name, org_id, role, prompt_id)

    delete_prompts(org.name, org_id, role, prompt_id, scope=user_id)

    return jsonify({"message": "Prompt updated successfully"}), 200

@main.route('/api/fetch_prompt_addons', methods=["GET"])
@jwt_required()
def fetch_prompt_addons():
    """
    Fetch prompts associated with the current user where scope is the user
    id, meaning the meeting has been added onto or the user created the meeting type themselves.
    """
    
    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']
    role = claims['sub']['role']

    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401
        
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    org = Organization.query.get(org_id)

    print("ARGS: ", org.name, org_id, user_id)
    prompts = fetch_prompts(org.name, org_id, scope=user_id)
    logging.info(prompts)

    if prompts == None:
        return jsonify({"error": "No prompts found"}), 404
    else:
        prompts_list = [{"prompt_id": str(m["_id"]), "default_prompts": m["default_prompts"], "type": m["type_name"], "description": m["description"]} for m in prompts]
        print(prompts_list)

        return jsonify({"prompts": prompts_list}), 200
    

@main.route('/api/add_personal_prompt_modification', methods=["POST"])
@jwt_required()
def add_personal_prompt_modification():
    """
    Manager add onto the end of a company-wide meeting type.
    """

    # Extract JWT claims
    claims = verify_jwt_in_request()[1]
    org_id = claims['sub'].get('org_id')
    user_id = claims['sub'].get('user_id')
    role = claims['sub'].get('role')

    # Check for valid org_id and user_id
    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401

    # Retrieve the current user
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    # Retrieve the organization
    org = Organization.query.get(org_id)
    if not org:
        return jsonify({"error": "Organization not found"}), 404

    # Retrieve JSON data from the request
    addon_meeting_data = request.json
    print("new_meeting_type_data:", addon_meeting_data)

    # Validate the input data
    required_fields = ["type_name", "default_prompts"]
    for field in required_fields:
        if field not in addon_meeting_data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    # You might want to add more validation here (e.g., check data types, lengths)

    # Call the function to add the new meeting type
    try:
        add_new_meeting_type(
            org_name=org.name,
            org_id=org_id,
            role=role,
            meeting_type_data=addon_meeting_data,
            scope=user_id
        )
    except Exception as e:
        print(f"Error adding new meeting type: {e}")
        return jsonify({"error": "Failed to add new meeting type"}), 500

    return jsonify({"message": "Meeting type added successfully"}), 200


@main.route('/api/chat_manager', methods=['POST'])
@jwt_required()
def chat_manager():
    """
    Chat endpoint, intakes the manager's selected employees to ask a question about.
    """
    
    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']

    if not org_id or not user_id:
        return jsonify({
            "error": "Please log in to access this route",
            "next_step": "login"
        }), 401

    user = User.query.get(user_id)
    org = Organization.query.get(org_id)

    org_name = org.name

    print(org_name)

    # Get the JSON data from the request
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    messages = data.get('messages')
    employee_ids = data.get('selectedEmployees')


    print(f"Messages: {messages}")
    print(f"Employees: {employee_ids}")

    if not messages:
        return jsonify({"error": "Missing 'messages' in request"}), 400

    # Process the messages and page URL
    try:
        reply = str(generate_ai_reply(messages, 
                                      user_id, 
                                      org_name, 
                                      org_id=org_id, 
                                      employee_ids=employee_ids))
        
    except Exception as e:
        print(f"Error generating AI reply: {e}")
        return jsonify({"error": "Failed to generate AI reply"}), 500

    return jsonify({"reply": reply}), 200


@main.route('/api/view_meetings/oneonone', methods=["GET"])
@jwt_required()
def get_manager_oneonones():
    """
    Get all one on one meetings associated with the manager (current user)
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

    manager = User.query.get(user_id)
    org = Organization.query.get(org_id)
    
    attendee_info = {"manager_id": user_id}

    meetings = get_one_on_ones(org.name, org_id, attendee_info)

    meetings_list = [{"meeting_id": str(m["_id"]), "date": m["date"], "duration": m["meeting_duration"], "type": m["type_name"], "attendees": m["attendees"], "summary": m["summary"]["Meeting Summary"]} for m in meetings]

    logging.info("MEETING LIST:", meetings_list)

    return jsonify({"manager": {"id": manager.id, "first_name": manager.first_name, "last_name": manager.last_name}, "meetings": meetings_list}), 200

@main.route('/api/fetch_prompts', methods=["GET"])
@jwt_required()
def fetch_prompts_for_company():
    """
    Fetch company wide prompts to be used by a manager.
    """
    
    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']
    role = claims['sub']['role']

    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401
        
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    org = Organization.query.get(org_id)

    print("Arguments: ", org.name, org_id, role)
    prompts = fetch_prompts(org.name, org_id, scope="company_wide")

    if prompts == None:
        return jsonify({"error": "No prompts found"}), 404
    else:
        prompts_list = [{"prompt_id": str(m["_id"]), "company_prompts": m["default_prompts"], "type": m["type_name"], "description": m["description"]} for m in prompts]

        return jsonify({"prompts": prompts_list}), 200
    

@main.route('/api/delete_prompt/<prompt_id>', methods=["GET"])
@jwt_required()
def delete_prompt_main(prompt_id):
    """
    Given prompt id from the frontend, look it up and delete it.
    """

    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']
    role = claims['sub']['role']

    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401
        
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    org = Organization.query.get(org_id)

    print("Deleting prompt with arguments: ", org.name, org_id, role, prompt_id)

    delete_prompts(org.name, org_id, role, prompt_id, scope=user_id)

    return jsonify({"message": "Prompt updated successfully"}), 200


@main.route('/api/update_meeting_notes', methods=["POST"])
@jwt_required()
def update_meeting_notes():
    """
    Given a meeting_id and some notes from the frontend, add them to the user's 
    meeting and save in MongoDB.
    """

    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']
    role = claims['sub']['role']

    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401
        
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    org = Organization.query.get(org_id)

    data = request.json

    meeting_id = data.get("meeting_id")
    notes = data.get("notes")
    
    update_notes(org.name, meeting_id, notes, collection_name="Meetings")

    return jsonify({"message": "Prompt updated successfully"}), 200

# Define the new route
@main.route("/api/start-bot", methods=["POST"])
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

        # Bot configuration to be sent to the external API
        payload = {
            "meeting_url": meeting_url,
            "bot_name": "Morph Meeting Recorder",
            "recording_mode": "audio_only",
            "join_at": join_at
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
    
@main.route("/api/webhook", methods=["POST"])
def webhook():
    """
    Listener to receive updates from Recall meeting bot.
    """
    headers = request.headers
    payload = request.get_data(as_text=True)  # Retrieve raw body text for verification
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
    
    try:
        # Verify the webhook using the secret key
        wh = Webhook(WEBHOOK_SECRET)
        wh.verify(payload, headers)

        # Extract the JSON payload from the incoming request
        data = request.json

        # Check what event was triggered
        event = data.get("event")
        
        if event == "bot.status_change":
            # Handle bot status change event
            bot_id = data["data"]["bot_id"]
            status_info = data["data"]["status"]
            status_code = status_info.get("code")
            status_time = status_info.get("created_at")
            sub_code = status_info.get("sub_code")
            message = status_info.get("message")
            recording_id = status_info.get("recording_id")  # May be absent

            logging.info(f"Bot {bot_id} status changed: {status_code} at {status_time}")

            # Retrieve the bot record from the database
            bot_record = BotRecord.query.filter_by(bot_id=bot_id).first()
            if not bot_record:
                logging.error(f"Bot record not found for bot_id {bot_id}")
                return jsonify({"error": "Bot record not found for bot_id"}), 404

            # Update the bot_record with the new status
            bot_record.status = status_code
            bot_record.status_time = status_time
            bot_record.sub_code = sub_code
            bot_record.message = message
            bot_record.recording_id = recording_id  # Ensure this field exists in your model

            db.session.commit()

            # Perform actions based on status_code
            if status_code == "done":
                # Call the "retrieve bot" method
                retrieve_bot(bot_id)

            # You can add additional status_code checks here if needed
            # For example, notify the user when recording starts, etc.

        else:
            logging.warning(f"Unhandled event type: {event}")
        
        # Return a success response to acknowledge receipt
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
                # Download the video from the 'video_url'
                video_response = requests.get(video_url, stream=True)
                if video_response.status_code == 200:
                    # Define the file path where you want to save the video
                    # You can customize the directory and filename as needed
                    video_filename = f"{bot_id}.mp4"
                    video_filepath = os.path.join('videos', video_filename)  # Ensure 'videos' directory exists

                    # Create the 'videos' directory if it doesn't exist
                    os.makedirs(os.path.dirname(video_filepath), exist_ok=True)

                    # Download and save the video file in chunks
                    with open(video_filepath, 'wb') as f:
                        for chunk in video_response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    logging.info(f"Video for bot {bot_id} downloaded and saved as {video_filepath}")

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
                        meeting_type=meeting_type,
                        user=attendees_info,
                        org=org_info,
                        meeting_name=bot_record.meeting_name
                    )

                else:
                    logging.error(f"Failed to download video for bot {bot_id}. Status code: {video_response.status_code}")
            else:
                logging.warning(f"No video_url available for bot {bot_id} at this time.")

        else:
            logging.error(f"Failed to retrieve bot {bot_id}. Response: {response_data}")

    except Exception as e:
        logging.error(f"Error retrieving bot {bot_id}: {e}")

@main.route("/api/get_employees_by_manager", methods=["GET"])
@jwt_required()
def get_employees_by_manager():
    """
    GET request:

        - Receives: JWT Token (with manager_id in claims)
        - Returns: List of direct reports for the authenticated manager
        
        Response example:
        {
            "reports": [
                {
                    "id": 1,
                    "first_name": "John",
                    "last_name": "Doe",
                    "email": "john.doe@example.com"
                },
                {
                    "id": 2,
                    "first_name": "Jane",
                    "last_name": "Smith",
                    "email": "jane.smith@example.com"
                }
            ]
        }
    """
    claims = verify_jwt_in_request()[1]
    manager_id = claims['sub']['user_id']  # Extract the manager's user ID from the token

    # Query the Reports model for all direct reports of this manager
    direct_reports = Reports.query.filter_by(manager_id=manager_id).all()

    # If no direct reports are found, return an empty list
    if not direct_reports:
        return jsonify({"reports": []}), 200

    # Prepare the list of direct reports
    reports_list = []
    for report in direct_reports:
        report_user = User.query.get(report.report_id)
        if report_user:
            reports_list.append({
                "id": report_user.id,
                "first_name": report_user.first_name,
                "last_name": report_user.last_name,
                "email": report_user.email
            })

    return jsonify({"reports": reports_list}), 200

@main.route("/api/test", methods=["GET"])
def test():
    
    import requests

    api_key = os.getenv("RECALL_API_KEY")  # Ensure this is set in your environment

    headers = {
        "accept": "application/json",
        "Authorization": api_key
    }

    bot_id = "9cc615ea-3b51-48c2-8f2b-95d6d5ebead1"

    url = f"https://us-west-2.recall.ai/api/v1/bot/{bot_id}"

    # Make the GET request to retrieve bot data
    response = requests.get(url, headers=headers)
    response_data = response.json()

    video_url = response_data.get("video_url")

    if video_url:
                # Download the video from the 'video_url'
        video_response = requests.get(video_url, stream=True)

        if video_response.status_code == 200:
            # Define the file path where you want to save the video
            # You can customize the directory and filename as needed
            video_filename = f"{bot_id}.mp4"
            video_filepath = os.path.join('videos', video_filename)  # Ensure 'videos' directory exists

            # Create the 'videos' directory if it doesn't exist
            os.makedirs(os.path.dirname(video_filepath), exist_ok=True)

            # Download and save the video file in chunks
            with open(video_filepath, 'wb') as f:
                for chunk in video_response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            attendees_info = {
                        "first_name": "Daniel",
                        "last_name": "Hill",
                        "email": "danielthill23@gmail.com",
                        "user_id": 167,
                        "role": "Manager"
                    }

            org_info = {"name": "BlenderProducts",
                        "org_id": 1}
    
            # Call the Celery task to process the video
            process_recall_video.delay(
                video_filepath=video_filepath,
                bot_id=bot_id,
                user=attendees_info,
                org=org_info,
                meeting_name="Teams/Zoom Meeting"
            )
            
            return jsonify({"success": "Call successful"}), 200

        else:
            print(f"Vid status code: {video_response.status_code}")
            
            return jsonify({"error": "Call was not successful, vid status code"}), 404


    else:
        print("No vid url")

        return jsonify({"error": "Call was not successful, no vid url"}), 404

