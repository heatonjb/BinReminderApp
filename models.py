from database import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import secrets
import logging
import pytz

logger = logging.getLogger(__name__)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    postcode = db.Column(db.String(10), nullable=True)
    password_hash = db.Column(db.String(256))
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    first_login = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    schedules = db.relationship('BinSchedule', backref='user', lazy=True)
    notification_type = db.Column(db.String(10), default='both', nullable=False)
    notification_time = db.Column(db.Integer, default=16, nullable=False)

    # Evening notification preferences
    evening_notification = db.Column(db.Boolean, default=True, nullable=False)
    evening_notification_time = db.Column(db.Integer, default=18, nullable=False)
    evening_notification_type = db.Column(db.String(10), default='both', nullable=False)

    # Morning notification preferences
    morning_notification = db.Column(db.Boolean, default=True, nullable=False)
    morning_notification_time = db.Column(db.Integer, default=7, nullable=False)
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

# Add new model for postcode-based collection schedules
class PostcodeSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    postcode = db.Column(db.String(10), nullable=False)
    bin_type = db.Column(db.String(20), nullable=False)  # 'refuse', 'recycling', or 'garden_waste'
    collection_day = db.Column(db.String(10), nullable=False)  # Monday, Tuesday, etc.
    frequency = db.Column(db.String(20), nullable=False)  # 'weekly' or 'biweekly'
    last_collection = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get_next_collection(collection_day, last_collection, frequency):
        """Calculate next collection date based on collection day and frequency."""
        days = {
            'Monday': 0, 'Tuesday': 1, 'Wednesday': 2,
            'Thursday': 3, 'Friday': 4, 'Saturday': 5, 'Sunday': 6
        }
        today = datetime.now(pytz.timezone('GMT'))
        target_day = days[collection_day]
        days_ahead = target_day - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        next_collection = today + timedelta(days=days_ahead)

        if frequency == 'biweekly':
            # If next collection is less than 14 days from last collection, add a week
            if (next_collection - last_collection).days < 14:
                next_collection += timedelta(days=7)

        return next_collection

class BinSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    bin_type = db.Column(db.String(20), nullable=False)
    frequency = db.Column(db.String(20), nullable=False)
    next_collection = db.Column(db.DateTime, nullable=False)

class EmailLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sent_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    recipient_email = db.Column(db.String(120), nullable=False)
    bin_type = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(10), nullable=False)
    error_message = db.Column(db.Text, nullable=True)

class SMSTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    template_text = db.Column(db.Text, nullable=False)
    description = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def render(self, **kwargs):
        """
        Render the template with provided variables.
        Example: template.render(bin_type='recycling', collection_date='2025-01-11')
        """
        try:
            return self.template_text.format(**kwargs)
        except KeyError as e:
            logger.error(f"Missing template variable: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Template rendering error: {str(e)}")
            return None