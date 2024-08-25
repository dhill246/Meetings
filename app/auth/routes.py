from flask import render_template, redirect, url_for, request, session
from flask_login import login_user
from ..models import Organization, User, db
from werkzeug.security import generate_password_hash
import logging
from . import auth
import os

@auth.route('/org', methods=['GET', 'POST'])
def org():
    if request.method == 'POST':
        org_name = request.form['org_name']
        password = request.form['password']

        logging.info(f"Received attempted login from {org_name}. Looking them up.")
        organization = Organization.query.filter_by(name=org_name).first()

        if organization and organization.check_password(password):
            logging.info("Found them.")
            session["org_id"] = organization.id
            logging.info(f"\nUser from {org_name} logged in.")

            return redirect(url_for('auth.signup'))
        
        else:
            return 'Invalid credentials'
    
    return render_template('org.html')

@auth.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()

        # If user exists, and passwords match
        if user and user.check_password(password):
            # Put user into the session
            login_user(user)
            print("Logged user in, redirecting to main")
            
            return redirect(url_for("main.home"))
        
        else:
            return "Incorrect password"

    return render_template("login.html")

@auth.route("/signup", methods=["GET", "POST"])
def signup():
    organization_id = session.get("org_id")
    print(f"Found org id: {organization_id}")

    if not organization_id:
        return redirect(url_for("auth.org"))

    if request.method == "POST":
        print(f"Method post hit")
        first_name = request.form["first_name"]
        last_name = request.form["last_name"]
        email = request.form["email"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        # Make sure all fields have been submitted
        if not email or not password or not confirm_password or not first_name or not last_name:
            return "Please make sure all fields are filled out."
        
        # Make sure passwords match
        elif password != confirm_password:
            return "Passwords do not match. Please try again."
        else:
            # Query user table by email to find out if the user already
            # has an account
            print(f"Checking if user exists.")

            existing_user = User.query.filter_by(email=email).first()

            # Create new user if they don't exist
            if existing_user is None:
                print(f"User does not exist yet.")

                # Create a new user and add them to the database

                if organization_id:
                    print("Creating new user")
                    new_user = User(email=email, 
                                    password_hash=generate_password_hash(password),
                                    first_name=first_name,
                                    last_name=last_name,
                                    organization_id=organization_id)
                    
                    print("Committing to the database")
                    db.session.add(new_user)
                    db.session.commit()

                    print("User committed.")

                    session["_user_id"] = new_user.id

                    print("Redirecting home")
                    return redirect(url_for("main.home"))
                
                else:
                    return redirect(url_for("auth.org"))
            
            else:
                return "User exists. Please log in."
            
    return render_template("signup.html")

@auth.route('/logout', methods=["POST"])
def logout():
    session.pop('_user_id', None)
    return redirect(url_for('auth.login'))