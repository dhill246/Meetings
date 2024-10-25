from . import admin
from flask import jsonify, request
from flask_jwt_extended import jwt_required, verify_jwt_in_request
from ..models import Organization, User, db, Invites, Reports
from sqlalchemy.orm import aliased
from ..utils.mongo import get_meetings_last_month, duration_to_seconds
from ..utils.Emails import send_invite_email
from ..utils.openAI import generate_ai_reply
import secrets
from datetime import datetime
from ..utils.openAI import generate_ai_reply_for_meeting
import logging
from bson import ObjectId
from ..utils.mongo import get_all_manager_meetings, get_one_on_ones, get_all_employee_meetings, fetch_prompts, update_prompts, add_new_meeting_type, delete_prompts, get_recent_meetings, delete_meeting

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
    
    if role != "admin":
        return jsonify({"msg": "Admins only!"}), 403
    
    current_org = Organization.query.get(org_id)
    if not current_org:
        return jsonify({"error": "Organization not found"}), 404

    org_name = current_org.name
    
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404
    
    # Alias the User table to represent the manager
    Manager = aliased(User)

    # Query to get employees and their manager's id, first name, and last name
    employees_managers = (
        db.session.query(
            User.id.label("report_id"),
            User.first_name.label("employee_first_name"),
            User.last_name.label("employee_last_name"),
            User.email.label("employee_email"),
            Manager.id.label("manager_id"),
            Manager.first_name.label("manager_first_name"),
            Manager.last_name.label("manager_last_name")
        )
        .join(Reports, Reports.report_id == User.id)  # Join to get the reports relationship
        .join(Manager, Reports.manager_id == Manager.id)  # Join the User table again for manager info
        .filter(User.organization_id == org_id)
        .all()
    )
    
    print(employees_managers)  # For debugging purposes

    # Use a dictionary to aggregate managers per employee
    employees_dict = {}
    
    for em in employees_managers:
        # Skip specific report IDs if necessary
        if em.report_id in [167, 172]:
            continue
        
        if em.report_id not in employees_dict:
            # Fetch meetings data
            meetings_in_past_x_days = get_meetings_last_month(org_name, org_id, em.report_id, role="Report", days=30)

            # Number of meetings in the past month
            num_meetings_in_past_month = len(meetings_in_past_x_days)

            # Calculate average meeting length in minutes
            meeting_lengths = []
            for meeting in meetings_in_past_x_days:
                duration_str = meeting.get("meeting_duration", "0h 0m 0s")
                total_seconds = duration_to_seconds(duration_str)
                meeting_lengths.append(total_seconds)

            if len(meeting_lengths) == 0:
                average_length_minutes = 0
            else:
                average_length_minutes = round(sum(meeting_lengths) / len(meeting_lengths) / 60, 2)
            
            # Initialize employee entry with an empty list of managers
            employees_dict[em.report_id] = {
                "id": em.report_id, 
                "first_name": em.employee_first_name,  
                "last_name": em.employee_last_name,
                "email": em.employee_email,  
                "num_meetings": num_meetings_in_past_month,
                "average_length_minutes": average_length_minutes,
                "managers": []  # Initialize empty list for managers
            }
        
        # Append manager to the employee's managers list
        employees_dict[em.report_id]["managers"].append({
            "id": em.manager_id,
            "first_name": em.manager_first_name,
            "last_name": em.manager_last_name
        })
    
    # Convert the dictionary to a list
    employees = list(employees_dict.values())

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
    
    prompts_list = [{"prompt_id": str(m["_id"]), "default_prompts": m["default_prompts"], "type": m["type_name"]} for m in prompts]

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

@admin.route('/api/add_employee', methods=['POST'])
@jwt_required()
def add_employee():
    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']
    role = claims['sub']['role']

    if not org_id or not user_id:
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401

    if role != "admin":
        return jsonify({"msg": "Admins only!"}), 403

    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    org = Organization.query.get(org_id)

    # Get the JSON data from the request
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    email = data.get('email')
    first_name = data.get('first_name')
    last_name = data.get('last_name')
    manager_ids = data.get('manager_ids')  # Expecting a list of manager IDs

    if not manager_ids or not isinstance(manager_ids, list):
        return jsonify({"error": "Invalid manager_ids provided"}), 400

    # Create the new user
    new_user = User(
        email=email,
        organization_id=org_id,
        first_name=first_name,
        last_name=last_name
    )

    db.session.add(new_user)
    db.session.flush()  # Flush to get the new user's ID

    # Add multiple manager-report relationships
    for manager_id in manager_ids:
        new_report = Reports(manager_id=manager_id, report_id=new_user.id, organization_id=org_id)
        db.session.add(new_report)

    db.session.commit()

    return jsonify({"message": f"{new_user.first_name} {new_user.last_name} has been added as an employee."}), 201

@admin.route('/api/edit_employee/<int:employee_id>', methods=['PUT'])
@jwt_required()
def edit_employee(employee_id):
    logging.info(f"Editing employee with ID: {employee_id}")

    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']
    role = claims['sub']['role']

    logging.info(f"Claims: {claims}")


    if not org_id or not user_id:
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401

    if role != "admin":
        return jsonify({"msg": "Admins only!"}), 403

    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    org = Organization.query.get(org_id)

    employee = User.query.filter_by(id=employee_id, organization_id=org_id).first()

    if not employee:
        return jsonify({"error": "Employee not found in the organization."}), 404

    # Get the JSON data from the request
    data = request.get_json()
    logging.info(f"Received data: {data}")
    if not data:
        return jsonify({"error": "No data provided"}), 400

    email = data.get('email')
    manager_ids = data.get('manager_ids')  # Expecting a list of manager IDs

    if not email:
        return jsonify({"error": "Email is required"}), 400

    if not manager_ids or not isinstance(manager_ids, list):
        return jsonify({"error": "Invalid manager_ids provided"}), 400
    
    logging.info(f"Updating employee {employee_id} with email {email} and managers {manager_ids}")


    # Update employee details
    employee.email = email

    # Clear existing manager-report relationships
    Reports.query.filter_by(report_id=employee.id, organization_id=org_id).delete()

    # Add updated manager-report relationships
    for manager_id in manager_ids:
        new_report = Reports(manager_id=manager_id, report_id=employee.id, organization_id=org_id)
        db.session.add(new_report)

    db.session.commit()

    return jsonify({"message": f"{employee.first_name} {employee.last_name}'s details have been updated."}), 200

    
@admin.route('/api/delete_employee/<int:employee_id>', methods=['DELETE'])
@jwt_required()
def delete_employee(employee_id):
    logging.info(f"Deleting employee with ID: {employee_id}")

    # Get the JWT claims
    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']
    role = claims['sub']['role']

    logging.info(f"Claims: {claims}")

    # Check if the organization and user are valid
    if not org_id or not user_id:
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401

    # Only admins can delete employees
    if role != "admin":
        return jsonify({"msg": "Admins only!"}), 403

    # Find the current user
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    # Find the organization
    org = Organization.query.get(org_id)

    # Find the employee to be deleted, ensuring they belong to the same organization
    employee = User.query.filter_by(id=employee_id, organization_id=org_id).first()

    if not employee:
        return jsonify({"error": "Employee not found in the organization."}), 404

    try:
        # Delete any manager-report relationships for the employee
        Reports.query.filter_by(report_id=employee.id, organization_id=org_id).delete()

        # Now delete the employee from the User table
        db.session.delete(employee)
        db.session.commit()

        logging.info(f"Employee {employee_id} deleted successfully")
        return jsonify({"message": f"Employee {employee.first_name} {employee.last_name} has been deleted."}), 200

    except Exception as e:
        logging.error(f"Error while deleting employee {employee_id}: {e}")
        return jsonify({"error": "An error occurred while deleting the employee."}), 500

@admin.route('/api/delete_meeting/<string:meeting_id>', methods=['DELETE'])
@jwt_required()
def delete_meeting(meeting_id):
    logging.info(f"Deleting meeting with ID: {meeting_id}")

    # Get the JWT claims
    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']
    role = claims['sub']['role']

    logging.info(f"Claims: {claims}")

    # Check if the organization and user are valid
    if not org_id or not user_id:
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401

    # Only admins can delete meetings
    if role != "admin":
        return jsonify({"msg": "Admins only!"}), 403

    # Find the current user
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    # Find the organization
    org = Organization.query.get(org_id)

    try:
        # Ensure the provided meeting_id is a valid ObjectId
        meeting_object_id = ObjectId(meeting_id)

        # Perform the deletion from MongoDB
        result = delete_meeting(org.name, org_id, meeting_object_id, role)

        if result.deleted_count == 1:
            logging.info(f"Meeting {meeting_id} deleted successfully")
            return jsonify({"message": f"Meeting with ID {meeting_id} has been deleted."}), 200
        else:
            logging.error(f"Meeting with ID {meeting_id} not found or not deleted.")
            return jsonify({"error": f"Meeting with ID {meeting_id} not found or not deleted."}), 404

    except Exception as e:
        logging.error(f"Error while deleting meeting {meeting_id}: {e}")
        return jsonify({"error": "An error occurred while deleting the meeting."}), 500


@admin.route('/api/chat_admin', methods=['POST'])
@jwt_required()
def chat_admin():
# Get the JWT claims
    claims = verify_jwt_in_request()[1]
    org_id = claims['sub']['org_id']
    user_id = claims['sub']['user_id']
    role = claims['sub']['role']

    logging.info(f"Claims: {claims}")

    # Check if the organization and user are valid
    if not org_id or not user_id:
        return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401

    # Only admins can delete meetings
    if role != "admin":
        return jsonify({"msg": "Admins only!"}), 403

    # Find the current user
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    # Find the organization
    org = Organization.query.get(org_id)

    org_name = org.name

    # Get the JSON data from the request
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    messages = data.get('messages')
    employee_ids = data.get('selectedEmployees')
    manager_ids = data.get('selectedManagers')

    logging.info(f"Messages: {messages}")
    logging.info(f"Employees: {employee_ids}")
    logging.info(f"Managers: {manager_ids}")

    if not messages:
        return jsonify({"error": "Missing 'messages' in request"}), 400

    # Process the messages and page URL
    try:
        reply = str(generate_ai_reply(messages, 
                                      user_id, 
                                      org_name, 
                                      org_id=org_id, 
                                      employee_ids=employee_ids, 
                                      manager_ids=manager_ids))

    except Exception as e:
        print(f"Error generating AI reply: {e}")
        return jsonify({"error": "Failed to generate AI reply"}), 500

    return jsonify({"reply": reply}), 200
