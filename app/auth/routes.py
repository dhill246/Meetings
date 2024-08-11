from flask import render_template, redirect, url_for, request, session
from flask import current_app
from . import auth
import os

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':

        username = request.form['username']
        password = request.form['password']
        # user = User.query.filter_by(username=username).first()
        # if user is not None and user.check_password(password):
        if username == os.getenv("BLENDER_USERNAME") and password == os.getenv("BLENDER_PASSWORD"):
            session['username'] = username
            print(f"\nUser from {username} logged in.")
            return redirect(url_for('main.index'))
        else:
            return 'Invalid credentials'
    return render_template('login.html')

@auth.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('main.index'))