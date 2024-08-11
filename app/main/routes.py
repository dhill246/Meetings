from flask import render_template, redirect, url_for, request, session
from . import main
from ..utils.s3_utils import check_existing_s3_files
from datetime import datetime
from flask_socketio import emit
from functools import wraps

# Wrapper function to restrict access to pages
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@main.route('/', methods=["GET", "POST"])
@login_required
def index():
    # If post request is sent, get the specified username and date
    # then proceed to the recording page
    # Otherwise return the index page

    if request.method == "POST":
        username = request.form['username']
        firstname = request.form['firstname']
        lastname = request.form['lastname']

        # Get today's date
        today = datetime.now()

        # Format the date
        DATE = today.strftime("%m-%d-%Y")

        return redirect(url_for('main.record', username=username, firstname=firstname,
                                lastname=lastname, date=DATE))
    return render_template('index.html')

@main.route('/record')
@login_required
def record():
    # Save the username and date for passing to the recording template
    username = request.args.get('username', '')
    date = request.args.get('date', '')
    firstname = request.args.get('firstname', '')
    lastname = request.args.get('lastname', '')

    list_s3 = check_existing_s3_files()
    list_s3_webm = set(["/".join(x.rsplit("/", 1)[:-1]) for x in list_s3])

    if (f"{username}/{firstname}{lastname}/{date}" in list_s3_webm) or (f"Summary_{username}_{firstname}{lastname}_{date}.txt" in list_s3):
        return render_template('error.html')

    else:
        return render_template('record.html', username=username, date=date, firstname=firstname, lastname=lastname)
