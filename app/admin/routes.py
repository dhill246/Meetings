from . import admin
from flask import jsonify, request
from flask_jwt_extended import jwt_required, verify_jwt_in_request
from ..models import Organization, User, db, Invites
from ..utils.mongo import get_meetings_last_month, duration_to_seconds
from ..utils.Emails import send_invite_email
import secrets
from datetime import datetime
import logging
from bson import ObjectId
from ..utils.mongo import get_all_manager_meetings, get_one_on_ones, get_all_employee_meetings, get_meeting_by_id

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
