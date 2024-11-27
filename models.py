from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    password_hash = db.Column(db.String(256))
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    schedules = db.relationship('BinSchedule', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class BinSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    bin_type = db.Column(db.String(20), nullable=False)  # 'refuse' or 'recycling'
    frequency = db.Column(db.String(20), nullable=False)  # 'weekly' or 'biweekly'
    next_collection = db.Column(db.DateTime, nullable=False)

class EmailLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sent_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    recipient_email = db.Column(db.String(120), nullable=False)
    bin_type = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(10), nullable=False)  # 'success' or 'failure'
    error_message = db.Column(db.Text, nullable=True)
