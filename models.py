from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import secrets

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    password_hash = db.Column(db.String(256))
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    schedules = db.relationship('BinSchedule', backref='user', lazy=True)
    notification_type = db.Column(db.String(10), default='both', nullable=False)  # 'email', 'sms', or 'both'
    notification_time = db.Column(db.Integer, default=16, nullable=False)  # Hour of the day (0-23)

    # Evening notification preferences
    evening_notification = db.Column(db.Boolean, default=True, nullable=False)
    evening_notification_time = db.Column(db.Integer, default=18, nullable=False)  # 6:30 PM
    evening_notification_type = db.Column(db.String(10), default='both', nullable=False)

    # Morning notification preferences
    morning_notification = db.Column(db.Boolean, default=True, nullable=False)
    morning_notification_time = db.Column(db.Integer, default=7, nullable=False)  # 7:30 AM
    morning_notification_type = db.Column(db.String(10), default='both', nullable=False)

    # Referral system and SMS credits
    sms_credits = db.Column(db.Integer, default=6, nullable=False)
    referral_code = db.Column(db.String(10), unique=True, nullable=False)
    referred_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    referrals = db.relationship('User', 
                              backref=db.backref('referred_by', remote_side=[id]),
                              foreign_keys=[referred_by_id])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.referral_code:
            self.referral_code = self.generate_referral_code()

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @staticmethod
    def generate_referral_code():
        """Generate a unique 8-character referral code."""
        while True:
            code = secrets.token_hex(4)  # 8 characters
            if not User.query.filter_by(referral_code=code).first():
                return code

    def has_sms_credits(self):
        """Check if user has SMS credits available."""
        return self.sms_credits > 0

    def use_sms_credit(self):
        """Use one SMS credit if available."""
        if self.has_sms_credits():
            self.sms_credits -= 1
            db.session.commit()
            return True
        return False

    def add_credits(self, amount):
        """Add SMS credits to the user's account."""
        self.sms_credits += amount
        db.session.commit()

class BinSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    bin_type = db.Column(db.String(20), nullable=False)  # 'refuse', 'recycling', or 'garden_waste'
    frequency = db.Column(db.String(20), nullable=False)  # 'weekly' or 'biweekly'
    next_collection = db.Column(db.DateTime, nullable=False)

class EmailLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sent_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    recipient_email = db.Column(db.String(120), nullable=False)
    bin_type = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(10), nullable=False)  # 'success' or 'failure'
    error_message = db.Column(db.Text, nullable=True)