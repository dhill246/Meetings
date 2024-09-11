from flask import render_template, jsonify, redirect, url_for, request, session
from ..models import User, Reports, db, Organization
from . import main
from ..utils.s3_utils import check_existing_s3_files, read_text_file
from ..utils.mongo import get_oneonone_meetings
from datetime import datetime
from flask_socketio import emit
from functools import wraps
from botocore.exceptions import ClientError
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request

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


    meetings_list = [{"meeting_id": str(m["_id"]), "date": m["date"], "summary": m["summary"]["Meeting Summary"]} for m in meetings]

    return jsonify({"report": {"id": report.id, "first_name": report.first_name, "last_name": report.last_name}, "meetings": meetings_list}), 200

# @main.route('/api/meeting/<int:meeting_id>', methods=['GET'])
# @jwt_required()
# def view_meeting_details(meeting_id):
#     try:
#         claims = verify_jwt_in_request()[1]
#         org_id = claims['sub']['org_id']
#         user_id = claims['sub']['user_id']

#         if not org_id or not user_id:
#             print("Please log in to access this page.")
#             return jsonify({"error": "Please log in to access this route", "next_step": "login"}), 401
        
#         meeting = Meeting.query.get(meeting_id)

#         if not meeting:
#             return jsonify({"error": "Meeting not found."}), 404

#         # Extract report_id from the meeting object
#         report = User.query.get(meeting.report_id)
#         if not report:
#             return jsonify({"error": "Report not found."}), 404

#         meeting_summary = read_text_file(meeting.s3_summary_name)
#         formatted_summary = meeting_summary.replace('- ', '\n\n- ')

#         # Convert the Markdown text to HTML
#         meeting_summary_html = markdown.markdown(formatted_summary)

#         # return render_template('meeting_details.html', meeting_summary=meeting_summary_html, meeting=meeting, report=report)
#         return jsonify({
#             "meeting_summary_html": meeting_summary_html,
#             "meeting": {"id": meeting.id, "date": meeting.date, "summary": meeting.summary},
#             "report": {"id": report.id, "first_name": report.first_name, "last_name": report.last_name}
#         }), 200
    
#     except ClientError as e:
#         if e.response['Error']['Code'] == 'NoSuchKey':
#             return jsonify({"error": "File not found in S3 bucket"}), 404
#         else:
#             return jsonify({"error": "An unexpected error occurred"}), 500
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500
    

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