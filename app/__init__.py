from flask import Flask, redirect, request, jsonify
from flask_socketio import SocketIO
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, current_user, logout_user, login_required
import os
import logging
from .models import db, User
from .utils.logger_setup import configure_logging
from .main import main as main_blueprint
from .super_admin import super_admin as super_blueprint
from .auth import auth as auth_blueprint
from .admin import admin as admin_blueprint
from .marketing import marketing as marketing_blueprint
from .recall import recall as recall_blueprint
from config import Config
from .socket_events import register_events
from flask_cors import CORS
from flask_talisman import Talisman
from flask_jwt_extended import JWTManager

TRUSTED_DOMAIN = os.getenv('TRUSTED_DOMAIN')
WEBHOOK_DOMAIN = os.getenv('WEBHOOK_DOMAIN')
PRODUCTION_DOMAIN = os.getenv('PRODUCTION_DOMAIN')
STAGING_DOMAIN = os.getenv('STAGING_DOMAIN')
CURRENT_ENV = os.getenv("FLASK_ENV")

socketio = SocketIO(cors_allowed_origins=TRUSTED_DOMAIN,
                    async_mode='eventlet')  # Create the SocketIO instance globally


def create_app():
    
    # Initialize Flask app
    app = Flask(__name__)

    # Load configuration from Config class
    app.config.from_object(Config)

    # Initialize jwt
    jwt = JWTManager(app)

    # Custom handler for expired tokens
    @jwt.expired_token_loader
    def my_expired_token_callback(jwt_header, jwt_payload):
        return jsonify({
            "msg": "Token has expired",
            "next_step": "login"
        }), 401
    

    # Initialize CORS with broad rule for /api/* routes
    CORS(app,
        supports_credentials=True,
        resources={r"/api/*": {"origins": TRUSTED_DOMAIN}})
    
    # Initialize csp
    # Talisman(app, content_security_policy=csp)

    # Initialize login manager
    login_manager = LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Redirection from Heroku domain to custom domain
    @app.before_request
    def before_request():

                # Redirect based on environment
        if "herokuapp" in request.host:
            if CURRENT_ENV == "production":
                return redirect(PRODUCTION_DOMAIN, code=301)
            elif CURRENT_ENV == "staging":
                return redirect(STAGING_DOMAIN, code=301)
            
    # Set up basic logging output for the app
    # logging.basicConfig(level=logging.INFO)

    # Initialize the database connection
    db.init_app(app)

    # Enable migration
    migrate = Migrate(app, db)

    # Initialize socket for listening
    # socketio = SocketIO(app)
    socketio.init_app(app)

    # Register blueprints
    app.register_blueprint(main_blueprint)
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(admin_blueprint)
    app.register_blueprint(marketing_blueprint)
    app.register_blueprint(super_blueprint)
    app.register_blueprint(recall_blueprint)

    register_events(socketio)  # Register your socket.io event handlers

    # Custom error handlers for API responses
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({"error": "Internal server error"}), 500

    return app