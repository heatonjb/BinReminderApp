import os
import re
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_mail import Mail, Message
from flask_migrate import Migrate
from sqlalchemy.orm import DeclarativeBase
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass

# Initialize extensions
db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()
mail = Mail()

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or "a secret key"
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Mail configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME')

# Initialize extensions with app
db.init_app(app)
migrate = Migrate(app, db)
login_manager.init_app(app)
mail.init_app(app)
login_manager.login_view = 'login'

# Initialize models
with app.app_context():
    from models import User, BinSchedule, EmailLog
    db.create_all()

# Import other dependencies after app and models are set up
from sms_notifications import send_sms_reminder, send_test_sms
from decorators import admin_required

# Initialize scheduler after all imports
from apscheduler.schedulers.background import BackgroundScheduler
scheduler = BackgroundScheduler()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def validate_phone(phone):
    phone = re.sub(r'[-\s()]', '', phone)
    return bool(re.match(r'^\+?1?\d{10,12}$', phone))

def validate_date(date_str):
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d')
        return date >= datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    except ValueError:
        return False

def send_collection_reminder(user_email, bin_type, collection_date):
    """Send email reminder with error handling and logging."""
    try:
        with app.app_context():
            msg = Message(
                subject=f'Bin Collection Reminder: {bin_type.title()} Collection Tomorrow',
                recipients=[user_email],
                body=f'''Dear Resident,

This is a reminder that your {bin_type} bin collection is scheduled for tomorrow, {collection_date.strftime('%A, %B %d, %Y')}.

Please ensure your bin is placed outside before the collection time.

Best regards,
Your Bin Collection Reminder Service'''
            )
            mail.send(msg)

            # Log successful email
            email_log = EmailLog(
                recipient_email=user_email,
                bin_type=bin_type,
                status='success'
            )
            db.session.add(email_log)
            db.session.commit()

            logger.info(f"Successfully sent reminder email to {user_email} for {bin_type} collection")
            return True
    except Exception as e:
        logger.error(f"Failed to send reminder email to {user_email}: {str(e)}")

        # Log failed email
        try:
            email_log = EmailLog(
                recipient_email=user_email,
                bin_type=bin_type,
                status='failure',
                error_message=str(e)
            )
            db.session.add(email_log)
            db.session.commit()
        except Exception as log_error:
            logger.error(f"Failed to log email error: {str(log_error)}")

        return False

def send_test_email(recipient_email):
    """Send a test email to verify email configuration."""
    try:
        with app.app_context():
            msg = Message(
                subject='Test Email - Bin Collection Reminder Service',
                recipients=[recipient_email],
                body='''This is a test email from your Bin Collection Reminder Service.

If you received this email, the email notification system is working correctly.

Best regards,
Your Bin Collection Reminder Service'''
            )
            mail.send(msg)
            logger.info(f"Successfully sent test email to {recipient_email}")
            return True
    except Exception as e:
        logger.error(f"Failed to send test email: {str(e)}")
        return False

def check_upcoming_collections():
    """Check and send reminders for tomorrow's collections."""
    with app.app_context():
        try:
            tomorrow = datetime.now().date() + timedelta(days=1)
            schedules = BinSchedule.query.join(User).filter(
                BinSchedule.next_collection.between(
                    tomorrow,
                    tomorrow + timedelta(days=1)
                )
            ).all()

            logger.info(f"Found {len(schedules)} collections scheduled for tomorrow")

            for schedule in schedules:
                notification_sent = False

                # Send email if user wants email notifications
                if schedule.user.notification_type in ['email', 'both']:
                    email_sent = send_collection_reminder(
                        schedule.user.email,
                        schedule.bin_type,
                        schedule.next_collection
                    )
                    notification_sent = notification_sent or email_sent

                # Send SMS if user wants SMS notifications
                if schedule.user.notification_type in ['sms', 'both']:
                    sms_sent = send_sms_reminder(
                        schedule.user.phone,
                        schedule.bin_type,
                        schedule.next_collection
                    )
                    notification_sent = notification_sent or sms_sent

                if notification_sent:
                    # Update next collection date based on frequency
                    if schedule.frequency == 'weekly':
                        schedule.next_collection += timedelta(days=7)
                    else:  # biweekly
                        schedule.next_collection += timedelta(days=14)

                    try:
                        db.session.commit()
                        logger.info(f"Updated next collection date for user {schedule.user.email}")
                    except Exception as e:
                        db.session.rollback()
                        logger.error(f"Failed to update next collection date: {str(e)}")

        except Exception as e:
            logger.error(f"Error in check_upcoming_collections: {str(e)}")

# Start the scheduler with default time (4 PM)
scheduler.add_job(
    check_upcoming_collections,
    'cron',
    hour=16,
    id='check_upcoming_collections'
)
scheduler.start()
logger.info("Email notification scheduler started - will run daily at 4 PM")

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('home.html')

@app.route('/dashboard')
@login_required
def dashboard():
    schedules = BinSchedule.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', schedules=schedules)

@app.route('/test-email')
@login_required
def test_email_route():
    """Route to test email functionality."""
    if send_test_email(current_user.email):
        flash('Test email sent successfully! Please check your inbox.')
    else:
        flash('Failed to send test email. Please check the server logs.')
    return redirect(url_for('dashboard'))

@app.route('/calendar')
@login_required
def calendar_view():
    schedules = BinSchedule.query.filter_by(user_id=current_user.id).all()
    events = []

    for schedule in schedules:
        # Calculate all collections for the next 3 months
        current_date = schedule.next_collection
        end_date = datetime.now() + timedelta(days=90)

        while current_date <= end_date:
            events.append({
                'title': f"{schedule.bin_type.title()} Collection",
                'start': current_date.strftime('%Y-%m-%d'),
                'binType': schedule.bin_type,
                'allDay': True
            })

            # Add next collection based on frequency
            if schedule.frequency == 'weekly':
                current_date += timedelta(days=7)
            else:  # biweekly
                current_date += timedelta(days=14)

    return render_template('calendar.html', events=events)

@app.route('/test-sms')
@login_required
def test_sms():
    """Route to test SMS functionality."""
    if send_test_sms(current_user.phone):
        flash('Test SMS sent successfully! Please check your phone.')
    else:
        flash('Failed to send test SMS. Please check the server logs.')
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            email = request.form.get('email')
            password = request.form.get('password')

            if not email or not password:
                logger.warning("Login attempt with missing credentials")
                flash('Please provide both email and password')
                return render_template('auth/login.html')

            user = User.query.filter_by(email=email).first()

            if not user:
                logger.warning(f"Login attempt failed: No user found with email {email}")
                flash('Invalid email or password')
                return render_template('auth/login.html')

            if user.check_password(password):
                login_user(user)
                logger.info(f"User {email} logged in successfully")
                return redirect(url_for('dashboard'))

            logger.warning(f"Login attempt failed: Invalid password for user {email}")
            flash('Invalid email or password')
        except Exception as e:
            logger.error(f"Error during login: {str(e)}")
            flash('An error occurred during login. Please try again.')
            db.session.rollback()

    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            email = request.form.get('email')
            phone = request.form.get('phone')
            password = request.form.get('password')

            if User.query.filter_by(email=email).first():
                flash('Email already registered')
                return redirect(url_for('register'))

            if not validate_phone(phone):
                flash('Invalid phone number format. Please use a valid format (e.g., +1234567890)')
                return redirect(url_for('register'))

            user = User(email=email, phone=phone)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            return redirect(url_for('login'))
        except Exception as e:
            logger.error(f"Error during registration: {str(e)}")
            flash('An error occurred during registration. Please try again.')
            db.session.rollback()

    return render_template('auth/register.html')

@app.route('/schedule/update', methods=['POST'])
@login_required
def update_schedule():
    try:
        bin_type = request.form.get('bin_type')
        frequency = request.form.get('frequency')
        next_collection_str = request.form.get('next_collection')

        if not validate_date(next_collection_str):
            flash('Invalid date. Please select a date from today onwards.')
            return redirect(url_for('dashboard'))

        if frequency not in ['weekly', 'biweekly']:
            flash('Invalid frequency selected')
            return redirect(url_for('dashboard'))

        next_collection = datetime.strptime(next_collection_str, '%Y-%m-%d')

        schedule = BinSchedule.query.filter_by(
            user_id=current_user.id,
            bin_type=bin_type
        ).first()

        if schedule:
            schedule.frequency = frequency
            schedule.next_collection = next_collection
        else:
            schedule = BinSchedule(
                user_id=current_user.id,
                bin_type=bin_type,
                frequency=frequency,
                next_collection=next_collection
            )
            db.session.add(schedule)

        db.session.commit()
        flash(f'{bin_type.title()} bin schedule updated successfully')
    except Exception as e:
        logger.error(f"Error updating schedule: {str(e)}")
        db.session.rollback()
        flash('An error occurred while updating the schedule')

    return redirect(url_for('dashboard'))

@app.route('/notification-preferences', methods=['POST'])
@login_required
def update_notification_preferences():
    try:
        notification_type = request.form.get('notification_type')
        notification_time = request.form.get('notification_time')

        if notification_type not in ['email', 'sms', 'both']:
            logger.warning(f"Invalid notification type selected: {notification_type}")
            flash('Invalid notification type selected')
            return redirect(url_for('dashboard'))

        try:
            notification_time = int(notification_time)
            if not (0 <= notification_time <= 23):
                raise ValueError("Time must be between 0 and 23")
        except ValueError as e:
            logger.warning(f"Invalid notification time selected: {notification_time}")
            flash('Invalid notification time selected')
            return redirect(url_for('dashboard'))

        current_user.notification_type = notification_type
        current_user.notification_time = notification_time

        db.session.commit()
        logger.info(f"Updated notification preferences for user {current_user.email}")

        # Update scheduler
        try:
            # Remove existing job if it exists
            try:
                scheduler.remove_job('check_upcoming_collections')
                logger.info("Removed existing notification job")
            except Exception as e:
                logger.warning(f"No existing job to remove: {str(e)}")

            # Add new job with updated time
            scheduler.add_job(
                check_upcoming_collections,
                'cron',
                hour=notification_time,
                id='check_upcoming_collections'
            )

            logger.info(f"Notification schedule updated to run at {notification_time}:00")
            flash('Notification preferences updated successfully')
        except Exception as e:
            logger.error(f"Error updating notification schedule: {str(e)}")
            flash('Notification preferences saved, but schedule update failed')

        return redirect(url_for('dashboard'))

    except Exception as e:
        logger.error(f"Unexpected error in update_notification_preferences: {str(e)}")
        db.session.rollback()
        flash('An unexpected error occurred')
        return redirect(url_for('dashboard'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/make_admin')
@login_required
def make_admin():
    if current_user.email == User.query.order_by(User.id.asc()).first().email:
        current_user.is_admin = True
        db.session.commit()
        flash('Admin privileges granted')
    return redirect(url_for('dashboard'))

# Import admin routes after all app setup is complete
with app.app_context():
    import admin_routes

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)