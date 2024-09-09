from . import admin
from flask import jsonify
from flask_jwt_extended import jwt_required, verify_jwt_in_request
from ..models import Organization, User, db
from ..utils.mongo import get_meetings_last_month, duration_to_seconds

@admin.route('/api/get_managers', methods=["GET"])
@jwt_required()
def get_mananagers():
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
        User.organization_id == 1,
        User.password_hash.isnot(None)
    ).all()

    managers = []

    for manager in managers_list_db:

        meetings_in_past_x_days = get_meetings_last_month(org_name, org_id, manager.id, days=30)

        # Number of meetings in the past month divided by the number of direct reports
        num_meetings_in_past_month = len(meetings_in_past_x_days)

        # Average length of 1:1 meeting in last month
        meeting_lengths = []
        for meeting in meetings_in_past_x_days:
            duration_str = meeting.get("meeting_duration", "0h 0m 0s")
            total_seconds = duration_to_seconds(duration_str)
            meeting_lengths.append(total_seconds)

        average_length_minutes = sum(meeting_lengths) / len(meeting_lengths) / 60        

        managers.append({"id": manager.id, 
                         "first_name": manager.first_name, 
                         "last_name": manager.last_name,
                         "num_meetings": num_meetings_in_past_month,
                         "average_length_minutes": average_length_minutes,
                         "num_reports": len(manager.managed_reports)})

    return jsonify({"current_user": int(current_user.get_id()), "managers": managers}), 200