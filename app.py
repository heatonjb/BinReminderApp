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

def check_upcoming_collections(notification_time='evening'):
    """Check and send reminders for tomorrow's collections."""
    with app.app_context():
        try:
            if notification_time == 'evening':
                # For evening notifications, check tomorrow's collections
                target_date = datetime.now().date() + timedelta(days=1)
            else:
                # For morning notifications, check today's collections
                target_date = datetime.now().date()

            schedules = BinSchedule.query.join(User).filter(
                BinSchedule.next_collection.between(
                    target_date,
                    target_date + timedelta(days=1)
                )
            ).all()

            logger.info(f"Found {len(schedules)} collections scheduled for {'tomorrow' if notification_time == 'evening' else 'today'}")

            for schedule in schedules:
                notification_sent = False
                user = schedule.user

                # Determine which notification preferences to use
                if notification_time == 'evening':
                    should_notify = user.evening_notification
                    notification_type = user.evening_notification_type
                else:
                    should_notify = user.morning_notification
                    notification_type = user.morning_notification_type

                if should_notify:
                    # Send email if configured
                    if notification_type in ['email', 'both']:
                        email_sent = send_collection_reminder(
                            user.email,
                            schedule.bin_type,
                            schedule.next_collection
                        )
                        notification_sent = notification_sent or email_sent

                    # Send SMS if configured
                    if notification_type in ['sms', 'both']:
                        sms_sent = send_sms_reminder(
                            user.phone,
                            schedule.bin_type,
                            schedule.next_collection
                        )
                        notification_sent = notification_sent or sms_sent

                    if notification_sent and notification_time == 'evening':
                        # Update next collection date based on frequency
                        # Only update after evening notification
                        if schedule.frequency == 'weekly':
                            schedule.next_collection += timedelta(days=7)
                        else:  # biweekly
                            schedule.next_collection += timedelta(days=14)

                        try:
                            db.session.commit()
                            logger.info(f"Updated next collection date for user {user.email}")
                        except Exception as e:
                            db.session.rollback()
                            logger.error(f"Failed to update next collection date: {str(e)}")

        except Exception as e:
            logger.error(f"Error in check_upcoming_collections: {str(e)}")

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
                flash('Please provide both email and password')
                return render_template('auth/login.html')

            user = User.query.filter_by(email=email).first()

            if not user:
                flash('Invalid email or password')
                return render_template('auth/login.html')

            if not user.check_password(password):
                flash('Invalid email or password')
                return render_template('auth/login.html')

            login_user(user)
            return redirect(url_for('dashboard'))

        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            db.session.rollback()
            flash('An error occurred. Please try again.')

    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            email = request.form.get('email')
            phone = request.form.get('phone')
            password = request.form.get('password')
            referral_code = request.args.get('ref')  # Get referral code from URL

            if User.query.filter_by(email=email).first():
                flash('Email already registered')
                return redirect(url_for('register'))

            if not validate_phone(phone):
                flash('Invalid phone number format. Please use a valid format (e.g., +1234567890)')
                return redirect(url_for('register'))

            # Create new user with default 6 credits
            user = User(email=email, phone=phone, sms_credits=6)
            user.set_password(password)

            # Handle referral if present
            if referral_code:
                referrer = User.query.filter_by(referral_code=referral_code).first()
                if referrer:
                    user.referred_by_id = referrer.id
                    user.sms_credits = 10  # Bonus credits for being referred
                    referrer.sms_credits += 20  # Bonus credits for referrer
                    logger.info(f"User {email} referred by {referrer.email}")

            db.session.add(user)
            db.session.commit()

            # Send welcome email with referral link
            welcome_email = Message(
                'Welcome to Bin Collection Reminder Service',
                recipients=[email],
                body=f'''Welcome to the Bin Collection Reminder Service!

Your account has been created successfully. You have {user.sms_credits} SMS credits to start with.

Share your referral link with friends and earn more credits:
https://{os.environ.get('REPLIT_SLUG')}.repl.co/register?ref={user.referral_code}

- You'll get 20 SMS credits for each friend who signs up
- Your friends will get 10 SMS credits to start (4 extra credits)

Best regards,
Your Bin Collection Reminder Service'''
            )
            mail.send(welcome_email)

            return redirect(url_for('login'))
        except Exception as e:
            logger.error(f"Error during registration: {str(e)}")
            flash('An error occurred during registration. Please try again.')
            db.session.rollback()

    return render_template('auth/register.html', referral_code=request.args.get('ref'))

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
        # Evening notification preferences
        evening_notification = request.form.get('evening_notification') == 'on'
        evening_notification_time = request.form.get('evening_notification_time')
        evening_notification_type = request.form.get('evening_notification_type')

        # Morning notification preferences
        morning_notification = request.form.get('morning_notification') == 'on'
        morning_notification_time = request.form.get('morning_notification_time')
        morning_notification_type = request.form.get('morning_notification_type')

        # Validate evening notification settings
        if evening_notification:
            if evening_notification_type not in ['email', 'sms', 'both']:
                flash('Invalid evening notification type selected')
                return redirect(url_for('dashboard'))

            try:
                evening_notification_time = int(evening_notification_time)
                if not (12 <= evening_notification_time <= 22):
                    raise ValueError
            except (ValueError, TypeError):
                flash('Invalid evening notification time selected')
                return redirect(url_for('dashboard'))

        # Validate morning notification settings
        if morning_notification:
            if morning_notification_type not in ['email', 'sms', 'both']:
                flash('Invalid morning notification type selected')
                return redirect(url_for('dashboard'))

            try:
                morning_notification_time = int(morning_notification_time)
                if not (5 <= morning_notification_time <= 11):
                    raise ValueError
            except (ValueError, TypeError):
                flash('Invalid morning notification time selected')
                return redirect(url_for('dashboard'))

        # Update user preferences
        current_user.evening_notification = evening_notification
        current_user.evening_notification_time = evening_notification_time
        current_user.evening_notification_type = evening_notification_type
        current_user.morning_notification = morning_notification
        current_user.morning_notification_time = morning_notification_time
        current_user.morning_notification_type = morning_notification_type

        # Save to database
        db.session.commit()

        # Update scheduler jobs
        scheduler.remove_all_jobs()

        # Add evening notification job if enabled
        if evening_notification:
            scheduler.add_job(
                check_upcoming_collections,
                'cron',
                hour=evening_notification_time,
                id='evening_notifications',
                args=['evening']
            )

        # Add morning notification job if enabled
        if morning_notification:
            scheduler.add_job(
                check_upcoming_collections,
                'cron',
                hour=morning_notification_time,
                id='morning_notifications',
                args=['morning']
            )

        flash('Notification preferences updated successfully')
        return redirect(url_for('dashboard'))

    except Exception as e:
        logger.error(f"Error updating notification preferences: {str(e)}")
        db.session.rollback()
        flash('An error occurred while updating preferences')
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
    # Start the scheduler
    scheduler.start()
    logger.info("Notification scheduler started")

    app.run(host='0.0.0.0', port=5000)