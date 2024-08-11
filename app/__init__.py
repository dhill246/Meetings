from flask import Flask, redirect, request
from flask_socketio import SocketIO
from flask_migrate import Migrate
import os
import logging
from .models import db
from .utils.logger_setup import configure_logging
from .main import main as main_blueprint
from .auth import auth as auth_blueprint
from config import Config
from .socket_events import register_events


socketio = SocketIO()  # Create the SocketIO instance globally

def create_app():
    
    # Initialize Flask app
    app = Flask(__name__)

    # Load configuration from Config class
    app.config.from_object(Config)

    # Redirection from Heroku domain to custom domain
    # @app.before_request
    # def before_request():
    #     if "herokuapp" in request.host:
    #         return redirect("https://morphdatastrategies.com", code=301)

    # Set up basic logging output for the app
    # logging.basicConfig(level=logging.INFO)

    # Initialize the database connection
    db.init_app(app)

    # Initialize socket for listening
    # socketio = SocketIO(app)
    socketio.init_app(app)

    # Enable migration
    migrate = Migrate(app, db)

    # Register blueprints
    app.register_blueprint(main_blueprint)
    app.register_blueprint(auth_blueprint)

    register_events(socketio)  # Register your socket.io event handlers

    return app