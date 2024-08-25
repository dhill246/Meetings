from app import create_app
from ..models import db, Organization
from werkzeug.security import generate_password_hash

# Create the app and context
app = create_app()

def add_organization(org_name, password):
    with app.app_context():
        new_org = Organization(name=org_name, 
                                password_hash=generate_password_hash(password))
                        
        db.session.add(new_org)
        db.session.commit()

with app.app_context():
    # Create a new Organization instance
    add_organization("BlenderProducts", "MeetingSummaries16600")

    print(f"Organization added successfully.")
