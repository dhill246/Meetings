from . import admin
from flask import jsonify, request
from flask_jwt_extended import jwt_required, verify_jwt_in_request
from ..models import Organization, User, db, Invites
from ..utils.mongo import get_meetings_last_month, duration_to_seconds
from ..utils.Emails import send_invite_email
import secrets
from datetime import datetime
from ..utils.openAI import generate_ai_reply_for_meeting
import logging
from bson import ObjectId
from ..utils.mongo import get_all_manager_meetings, get_one_on_ones, get_all_employee_meetings, fetch_prompts, update_prompts, add_new_meeting_type, delete_prompts, get_recent_meetings

@admin.route('/api/get_managers', methods=["GET"])
@jwt_required()
def get_managers():
    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']
    role = claims['sub']['role']

    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401
    
    if not role == "admin":
        return jsonify({"msg": "Admins only!"}), 403
    
    current_org = Organization.query.get(org_id)
    org_name = current_org.name
    
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404
    
    managers_list_db = User.query.filter(
        User.organization_id == org_id,
        User.password_hash.isnot(None)
    ).all()

    managers = []

    for manager in managers_list_db:

        if manager.id == 167 or manager.id == 229:
            continue

        meetings_in_past_x_days = get_meetings_last_month(org_name, org_id, manager.id, role="Manager", days=30)

        # Number of meetings in the past month divided by the number of direct reports
        num_meetings_in_past_month = len(meetings_in_past_x_days)

        # Average length of 1:1 meeting in last month
        meeting_lengths = []
        for meeting in meetings_in_past_x_days:
            duration_str = meeting.get("meeting_duration", "0h 0m 0s")
            total_seconds = duration_to_seconds(duration_str)
            meeting_lengths.append(total_seconds)

        if len(meeting_lengths) == 0:
            average_length_minutes = 0
        else:
            average_length_minutes = round(sum(meeting_lengths) / len(meeting_lengths) / 60, 2)        

        managers.append({"id": manager.id, 
                         "first_name": manager.first_name, 
                         "last_name": manager.last_name,
                         "num_meetings": num_meetings_in_past_month,
                         "average_length_minutes": average_length_minutes,
                         "num_reports": len(manager.managed_reports)})

    return jsonify({"current_user": int(current_user.get_id()), "managers": managers}), 200

@admin.route('/api/get_employees', methods=["GET"])
@jwt_required()
def get_employees():
    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']
    role = claims['sub']['role']

    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401
    
    if not role == "admin":
        return jsonify({"msg": "Admins only!"}), 403
    
    current_org = Organization.query.get(org_id)
    org_name = current_org.name
    
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404
    
    employees_list = User.query.filter(
        User.organization_id == org_id,
    ).all()

    employees = []

    for employee in employees_list:

        if employee.id == 167 or employee.id == 172:
            continue

        meetings_in_past_x_days = get_meetings_last_month(org_name, org_id, employee.id, role="Report", days=30)

        # Number of meetings in the past month divided by the number of direct reports
        num_meetings_in_past_month = len(meetings_in_past_x_days)

        # Average length of 1:1 meeting in last month
        meeting_lengths = []
        for meeting in meetings_in_past_x_days:
            duration_str = meeting.get("meeting_duration", "0h 0m 0s")
            total_seconds = duration_to_seconds(duration_str)
            meeting_lengths.append(total_seconds)

        if len(meeting_lengths) == 0:
            average_length_minutes = 0
        else:
            average_length_minutes = round(sum(meeting_lengths) / len(meeting_lengths) / 60, 2)        

        employees.append({"id": employee.id, 
                         "first_name": employee.first_name, 
                         "last_name": employee.last_name,
                         "num_meetings": num_meetings_in_past_month,
                         "average_length_minutes": average_length_minutes})

    return jsonify({"current_user": int(current_user.get_id()), "employees": employees}), 200

@admin.route('/api/send_invite', methods=["POST"])
@jwt_required()
def send_invite():
    logging.info("Sending invite")

    claims = verify_jwt_in_request()[1]
    print("claims:", claims)
    org_id = claims['sub']['org_id']
    print("org_id:", org_id)
    user_id = claims['sub']['user_id']
    print("user_id:", user_id)
    role = claims['sub']['role']
    print("role:", role)

    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401
    
    if not role == "admin":
        return jsonify({"msg": "Admins only!"}), 403
    
    current_org = Organization.query.get(org_id)
    org_name = current_org.name

    data = request.get_json()
    email = data["managerEmail"]

    # Generate token for the invite
    token = secrets.token_urlsafe(16)
    print("token:", token)


    logging.info("Adding invite to database")
     # Add the existing user as a direct report
    new_invite = Invites(email=email, organization_id=org_id, token=token, date=datetime.now())
    db.session.add(new_invite)
    db.session.commit()

    logging.info("Sending invite email")
    send_invite_email(email, token, org_name)

    return jsonify({"message": "Invite sent successfully"}), 200



@admin.route('/api/verify-token', methods=["GET"])
def verify_token():
    token = request.args.get('token')

    if not token:
        return jsonify({"valid": False, "error": "No token provided"}), 400
    
     # Query the Invites table for the token
    invite = Invites.query.filter_by(token=token).first()

    if not invite:
        return jsonify({"valid": False, "error": "Invalid or expired token"}), 400

    # You can also add token expiration logic here if you want, for example:
    # Check if the token is older than a certain number of hours/days
    if (datetime.now() - invite.date).days > 7:  # Assuming tokens expire after 7 days
        return jsonify({"valid": False, "error": "Token has expired"}), 400

    # If valid, return the organization ID associated with the invite
    org_id = invite.organization_id
    return jsonify({"valid": True, "org_id": org_id}), 200


@admin.route('/api/manager/<int:manager_id>', methods=["GET"])
@jwt_required()
def get_manager(manager_id):
    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']
    role = claims['sub']['role']

    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401
    
    if not role == "admin":
        return jsonify({"msg": "Admins only!"}), 403
        
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404
    

    manager = User.query.get(manager_id)
    org = Organization.query.get(org_id)
    
    attendee_info = {"manager_id": manager_id}

    meetings = get_all_manager_meetings(org.name, org_id, attendee_info)

    meetings_list = [{"meeting_id": str(m["_id"]), "date": m["date"], "duration": m["meeting_duration"], "type": m["type_name"], "attendees": m["attendees"], "summary": m["summary"]["Meeting Summary"]} for m in meetings]

    return jsonify({"manager": {"id": manager.id, "first_name": manager.first_name, "last_name": manager.last_name}, "meetings": meetings_list}), 200

@admin.route('/api/employee/<int:employee_id>', methods=["GET"])
@jwt_required()
def get_employee(employee_id):
    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']
    role = claims['sub']['role']

    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401
    
    if not role == "admin":
        return jsonify({"msg": "Admins only!"}), 403
        
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404
    

    employee = User.query.get(employee_id)
    org = Organization.query.get(org_id)
    
    attendee_info = {"employee_id": employee_id}

    meetings = get_all_employee_meetings(org.name, org_id, attendee_info)

    meetings_list = [{"meeting_id": str(m["_id"]), "date": m["date"], "duration": m["meeting_duration"], "type": m["type_name"], "attendees": m["attendees"], "summary": m["summary"]["Meeting Summary"]} for m in meetings]

    return jsonify({"employee": {"id": employee.id, "first_name": employee.first_name, "last_name": employee.last_name}, "meetings": meetings_list}), 200


@admin.route('/api/manager/oneonones/<int:manager_id>', methods=["GET"])
@jwt_required()
def get_manager_oneonones(manager_id):
    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']
    role = claims['sub']['role']

    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401
    
    if not role == "admin":
        return jsonify({"msg": "Admins only!"}), 403
        
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    manager = User.query.get(manager_id)
    org = Organization.query.get(org_id)
    
    attendee_info = {"manager_id": manager_id}

    meetings = get_one_on_ones(org.name, org_id, attendee_info)

    meetings_list = [{"meeting_id": str(m["_id"]), "date": m["date"], "duration": m["meeting_duration"], "type": m["type_name"], "attendees": m["attendees"], "summary": m["summary"]["Meeting Summary"]} for m in meetings]

    return jsonify({"manager": {"id": manager.id, "first_name": manager.first_name, "last_name": manager.last_name}, "meetings": meetings_list}), 200

@admin.route('/api/fetch_prompts_admin', methods=["GET"])
@jwt_required()
def fetch_prompts_admin():
    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']
    role = claims['sub']['role']

    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401
    
    if not role == "admin":
        return jsonify({"msg": "Admins only!"}), 403
        
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
    
@admin.route('/api/update_prompt_admin/<prompt_id>', methods=["POST"])
@jwt_required()
def update_prompt(prompt_id):

    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']
    role = claims['sub']['role']

    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401
    
    if not role == "admin":
        return jsonify({"msg": "Admins only!"}), 403
        
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    org = Organization.query.get(org_id)

    # Retrieve JSON data from the request
    updated_data = request.json
    print("updated_data:", updated_data)

    update_prompts(org.name, org_id, role, prompt_id, updated_data, scope="company_wide")

    return jsonify({"message": "Prompt updated successfully"}), 200

@admin.route('/api/add_meeting_type_admin', methods=["POST"])
@jwt_required()
def add_meeting_type_admin():
    # Extract JWT claims
    claims = verify_jwt_in_request()[1]
    org_id = claims['sub'].get('org_id')
    user_id = claims['sub'].get('user_id')
    role = claims['sub'].get('role')

    # Check for valid org_id and user_id
    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401

    # Check if the user has admin privileges
    if role != "admin":
        return jsonify({"msg": "Admins only!"}), 403

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


@admin.route('/api/delete_prompt_admin/<prompt_id>', methods=["GET"])
@jwt_required()
def delete_prompt(prompt_id):

    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']
    role = claims['sub']['role']

    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401
    
    if not role == "admin":
        return jsonify({"msg": "Admins only!"}), 403
        
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    org = Organization.query.get(org_id)

    print("Deleting prompt with arguments: ", org.name, org_id, role, prompt_id)

    delete_prompts(org.name, org_id, role, prompt_id, scope="company_wide")

    return jsonify({"message": "Prompt updated successfully"}), 200


@admin.route('/api/prompts/<manager_id>', methods=["GET"])
@jwt_required()
def retreive_manager_prompts(manager_id):
    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']
    role = claims['sub']['role']

    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401
    
    if not role == "admin":
        return jsonify({"msg": "Admins only!"}), 403
        
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    org = Organization.query.get(org_id)

    prompts = fetch_prompts(org.name, org_id, int(manager_id))

    print("Prompts: ", prompts)

    manager = User.query.get(manager_id)

    if prompts == []:
        return jsonify({
            "prompts": [],
            "message": f"{manager.first_name} hasn't added any custom meeting types yet."
        }), 200    
    
    prompts_list = [{"prompt_id": str(m["_id"]), "personal_prompts": m["personal_prompts"], "type": m["type_name"]} for m in prompts]

    return jsonify({"prompts": prompts_list}), 200

@admin.route('/api/ten_most_recent_meetings', methods=["GET"])
def get_most_recent_meetings():
    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']
    role = claims['sub']['role']

    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401
    
    if not role == "admin":
        return jsonify({"msg": "Admins only!"}), 403
        
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    org = Organization.query.get(org_id)

    meetings = get_recent_meetings(org.name, org_id, "One-on-One", 10)

    meetings_list = [{"meeting_id": str(m["_id"]), "date": m["date"], "duration": m["meeting_duration"], "type": m["type_name"], "attendees": m["attendees"], "summary": m["summary"]["Meeting Summary"]} for m in meetings]

    return jsonify({"meetings": meetings_list}), 200

@admin.route('/api/test_prompt_chat', methods=['POST'])
@jwt_required()
def test_prompt_chat():
    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']
    role = claims['sub']['role']

    if not org_id or not user_id:
        print("Please log in to access this route.")
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401
    
    if not role == "admin":
        return jsonify({"msg": "Admins only!"}), 403
        
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    org = Organization.query.get(org_id)

    org_name = org.name

    # Get the JSON data from the request
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    prompt = data.get('prompt')
    meeting = data.get('meeting')
    page_url = data.get('pageUrl')

    if not meeting or not page_url:
        return jsonify({"error": "Missing 'messages' or 'pageUrl' in request"}), 400

    meeting_id = meeting.get("meeting_id")
    print(meeting_id)
    # Process the messages and page URL
    try:
        reply = str(generate_ai_reply_for_meeting(prompt, meeting_id, user_id, org_name, org_id=org_id))

    except Exception as e:
        print(f"Error generating AI reply: {e}")
        return jsonify({"error": "Failed to generate AI reply"}), 500

    return jsonify({"reply": reply}), 200


