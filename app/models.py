from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash
from sqlalchemy.orm import relationship
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class Organization(db.Model):
    __tablename__ = "organization"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(256))

    # Relationship to the User model
    users = relationship('User', backref='organization', lazy=True)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class User(db.Model, UserMixin):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(60), nullable=False)
    last_name = db.Column(db.String(60), nullable=False)
    email = db.Column(db.String(120))
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(60))

    # Foreign key
    organization_id = db.Column(db.Integer, db.ForeignKey("organization.id", name="fk_user_organization_id"), nullable=False)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.email}>"
    

class Reports(db.Model):
    __tablename__ = 'reports'
    manager_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    report_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey("organization.id", name="fk_user_organization_id"), nullable=True)

    __table_args__ = (
        db.PrimaryKeyConstraint('manager_id', 'report_id', 'organization_id'),
    )

    manager = relationship("User", foreign_keys=[manager_id], backref="managed_reports")
    report  = relationship("User", foreign_keys=[report_id], backref="direct_manager")

class Invites(db.Model):
    __tablename__ = 'invites'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    token = db.Column(db.String(256), nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.now)

    # Foreign keys to link to the manager and report
    organization_id = db.Column(db.Integer, db.ForeignKey("organization.id", name="fk_user_organization_id"), nullable=True)


class Subscribers(db.Model, UserMixin):
    __tablename__ = 'subscribers'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120))
    subscribed_on = db.Column(db.DateTime, default=datetime.now)

    def __repr__(self):
        return f"<Subscriber {self.email}>"
    
class BotRecord(db.Model):
    __tablename__ = 'bot_records'
    
    id = db.Column(db.Integer, primary_key=True)
    bot_id = db.Column(db.String(120), nullable=False)  # Bot ID from the external service
    meeting_url = db.Column(db.String(500), nullable=False)  # Meeting URL provided by the user
    meeting_name = db.Column(db.String(500), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', name='fk_botrecord_user_id'), nullable=False)  # Foreign key to User model
    org_id = db.Column(db.Integer, db.ForeignKey('organization.id', name='fk_botrecord_org_id'), nullable=False)  # Foreign key to Organization model
    created_at = db.Column(db.DateTime, default=datetime.now)  # Timestamp for when the bot was created
    updated_at = db.Column(db.DateTime, onupdate=datetime.now)  # Timestamp for updates
    
    # Relationships
    user = db.relationship('User', backref='bot_records', lazy=True)  # Relationship to User
    organization = db.relationship('Organization', backref='bot_records', lazy=True)  # Relationship to Organization

    def __repr__(self):
        return f"<BotRecord bot_id={self.bot_id} user_id={self.user_id} status={self.status}>"