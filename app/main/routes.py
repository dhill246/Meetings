from flask import render_template, redirect, url_for, request, session
from markupsafe import Markup
from flask_login import current_user, login_required
from ..models import User, Reports, Meeting, db
from . import main
from ..utils.s3_utils import check_existing_s3_files, read_text_file
from datetime import datetime
from flask_socketio import emit
from functools import wraps
import markdown

# Wrapper function to restrict access to pages
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        print("Checking for user_id")
        if ('_user_id' not in session):
            print("UserID not in session")

            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@main.route('/')
def landing_page():
    # return render_template('index.html')
    return redirect(url_for('main.home'))


@main.route('/home', methods=["GET", "POST"])
@login_required
def home():
    if not current_user.is_authenticated:
        print("Please log in to access this page.")
        return redirect(url_for('auth.login'))

    # If POST request is sent, get the specified report ID and proceed to the recording page
    if request.method == "POST":
        report_id = request.form.get("report_id")
        report = User.query.get(report_id)

        if report:
            today = datetime.now()
            DATE = today.strftime("%m-%d-%Y")

            return redirect(url_for('main.record',
                                    user_id=current_user.id,
                                    report_id=report_id,
                                    username=f"{current_user.first_name} {current_user.last_name}", 
                                    firstname=report.first_name,
                                    lastname=report.last_name, 
                                    date=DATE))
        else:
            print("Report not found.")
            return redirect(url_for('main.home'))

    # Get the current user's direct reports
    direct_reports = current_user.managed_reports

    # Debugging: Print direct_reports
    for report_relationship in direct_reports:
        print(f"Report ID: {report_relationship.report_id}, First Name: {report_relationship.report.first_name}, Last Name: {report_relationship.report.last_name}")

    return render_template('home.html', current_user=current_user, direct_reports=direct_reports)


@main.route("/add_report", methods=["POST"])
@login_required
def add_report():
    first_name = request.form.get("firstname")
    last_name = request.form.get("lastname")
    email = request.form.get("email")

    # Check if the user already exists in the database
    existing_user = User.query.filter_by(first_name=first_name, 
                                         last_name=last_name,
                                         email=email).first()

    if existing_user:
        # Check if the existing user is already a direct report
        existing_report = Reports.query.filter_by(manager_id=current_user.id, report_id=existing_user.id).first()
        
        if existing_report:
            print(f"{existing_user.first_name} {existing_user.last_name} is already your direct report.")
        else:
            # Add the existing user as a direct report
            new_report = Reports(manager_id=current_user.id, report_id=existing_user.id, organization_id=current_user.organization_id)
            db.session.add(new_report)
            db.session.commit()
            print(f"{existing_user.first_name} {existing_user.last_name} has been added as your direct report.")
    else:
        # Create a new user and add them as a direct report
        new_user = User(first_name=first_name, 
                        last_name=last_name, 
                        email=email,
                        organization_id=current_user.organization_id)
        db.session.add(new_user)
        db.session.commit()

        new_report = Reports(manager_id=current_user.id, report_id=new_user.id)
        db.session.add(new_report)
        db.session.commit()

    return redirect(url_for('main.home'))

@main.route("/remove_report/<int:report_id>", methods=["POST"])
@login_required
def remove_report(report_id):
    # Find the report relationship to remove
    report_relationship = Reports.query.filter_by(manager_id=current_user.id, report_id=report_id).first()

    if report_relationship:
        db.session.delete(report_relationship)
        db.session.commit()

    return redirect(url_for('main.home'))

@main.route("/view_meetings/<int:report_id>", methods=["GET"])
@login_required
def view_meetings(report_id):
    report = User.query.get(report_id)
    meetings = Meeting.query.filter_by(report_id=report_id).all()
    return render_template('dashboard.html', meetings=meetings, report=report)

@main.route('/meeting/<int:meeting_id>', methods=['GET'])
def view_meeting_details(meeting_id):
    meeting = Meeting.query.get(meeting_id)

    # Extract report_id from the meeting object
    report_id = meeting.report_id
    report = User.query.get(report_id)

    meeting_summary = read_text_file(meeting.s3_summary_name)

    formatted_summary = meeting_summary.replace('- ', '\n\n- ')

    # Convert the Markdown text to HTML
    meeting_summary_html = Markup(markdown.markdown(formatted_summary))

    return render_template('meeting_details.html', meeting_summary=meeting_summary_html, meeting=meeting, report=report)

@main.route('/record')
@login_required
def record():
    # Save the username and date for passing to the recording template
    user_id = request.args.get("user_id", "")
    report_id =  request.args.get("report_id", "")
    username = request.args.get('username', '')
    date = request.args.get('date', '')
    firstname = request.args.get('firstname', '')
    lastname = request.args.get('lastname', '')


    list_s3 = check_existing_s3_files()
    list_s3_webm = set(["/".join(x.rsplit("/", 1)[:-1]) for x in list_s3])

    if (f"{username}/{firstname}{lastname}/{date}" in list_s3_webm) or (f"Summary_{username}_{firstname}{lastname}_{date}.txt" in list_s3):
        return render_template('error.html')

    else:
        return render_template('record.html', user_id=user_id, report_id=report_id, username=username, date=date, firstname=firstname, lastname=lastname)
