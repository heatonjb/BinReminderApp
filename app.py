import os
import re
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import pytz
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from mailersend import emails
from sqlalchemy import func

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize scheduler with GMT timezone
scheduler = BackgroundScheduler()
gmt = pytz.timezone('GMT')
scheduler.configure(timezone=gmt)

def job_listener(event):
    if event.exception:
        logger.error(f'Job failed: {event.job_id}')
        logger.error(f'Exception: {event.exception}')
        logger.error(f'Traceback: {event.traceback}')
    else:
        logger.info(f'Job completed successfully: {event.job_id}')

scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

# Initialize extensions
from database import db
login_manager = LoginManager()

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or "a secret key"
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Initialize MailerSend client with error handling
try:
    mailer = emails.NewEmail(os.environ.get('MAILERSEND_API_KEY'))
except Exception as e:
    logger.error(f"Failed to initialize MailerSend: {str(e)}")
    mailer = None

# Initialize extensions with app
db.init_app(app)
migrate = Migrate(app, db)
login_manager.init_app(app)
login_manager.login_view = 'login'

# Import models
from models import User, BinSchedule, EmailLog, PostcodeSchedule, SMSTemplate, SMSLog

# Import other dependencies after app and models are set up
from sms_notifications import send_sms_reminder, send_test_sms
from decorators import admin_required

# Initialize database tables
with app.app_context():
    db.create_all()

def send_collection_reminder(user_email, bin_type, collection_date):
    """Send email reminder with error handling and logging."""
    try:
        if not mailer:
            raise Exception("MailerSend client not initialized")

        with app.app_context():
            user = User.query.filter_by(email=user_email).first()
            if not user:
                raise ValueError(f"User not found for email: {user_email}")

            invite_url = url_for('register', ref=user.referral_code, _external=True)

            # Mail content remains unchanged
            mail_body = f'''Dear Resident,

This is a reminder that your {bin_type} bin collection is scheduled for tomorrow, {collection_date.strftime('%A, %B %d, %Y')}.

Please ensure your bin is placed outside before the collection time.

Your Account Information:
------------------------
SMS Credits Balance: {user.sms_credits} credits
Want more credits? Share your referral link with friends!

Referral Program:
----------------
• You'll get 20 SMS credits for each friend who signs up
• Your friends will get 10 bonus SMS credits to start
• Share your unique referral link: {invite_url}

Best regards,
Your Bin Collection Reminder Service'''

            mail_data = {
                "from": {"email": os.environ.get('MAILERSEND_FROM_EMAIL')},
                "to": [{"email": user_email}],
                "subject": f'Bin Collection Reminder: {bin_type.title()} Collection Tomorrow',
                "text": mail_body
            }

            # Send email using MailerSend
            response = mailer.send(mail_data)

            if not response.status_code == 202:
                raise Exception(f"MailerSend API error: {response.text}")

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
        if not mailer:
            raise Exception("MailerSend client not initialized")

        with app.app_context():
            mail_data = {
                "from": {"email": os.environ.get('MAILERSEND_FROM_EMAIL')},
                "to": [{"email": recipient_email}],
                "subject": 'Test Email - Bin Collection Reminder Service',
                "text": '''This is a test email from your Bin Collection Reminder Service.

If you received this email, the email notification system is working correctly.

Best regards,
Your Bin Collection Reminder Service'''
            }

            response = mailer.send(mail_data)

            if not response.status_code == 202:
                raise Exception(f"MailerSend API error: {response.text}")

            logger.info(f"Successfully sent test email to {recipient_email}")
            return True
    except Exception as e:
        logger.error(f"Failed to send test email: {str(e)}")
        return False

def validate_phone(phone):
    phone = re.sub(r'[-\s()]', '', phone)
    return bool(re.match(r'^\+?1?\d{10,12}$', phone))

def validate_date(date_str):
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d')
        gmt = pytz.timezone('GMT')
        current_time = datetime.now(gmt)
        return date.replace(tzinfo=gmt) >= current_time.replace(hour=0, minute=0, second=0, microsecond=0)
    except ValueError:
        return False

def check_upcoming_collections(notification_time='evening'):
    """Check and send reminders for tomorrow's collections using GMT timezone."""
    with app.app_context():
        try:
            gmt = pytz.timezone('GMT')
            current_time = datetime.now(gmt)
            logger.info(f"Starting collection check at {current_time} GMT")

            if notification_time == 'evening':
                # For evening notifications, check tomorrow's collections
                target_date = (current_time + timedelta(days=1)).date()
                logger.info(f"Checking tomorrow's collections for {target_date}")
            else:
                # For morning notifications, check today's collections
                target_date = current_time.date()
                logger.info(f"Checking today's collections for {target_date}")

            schedules = BinSchedule.query.join(User).filter(
                BinSchedule.next_collection.between(
                    target_date,
                    target_date + timedelta(days=1)
                )
            ).all()

            logger.info(f"Found {len(schedules)} collections scheduled for {target_date}")

            for schedule in schedules:
                notification_sent = False
                user = schedule.user
                logger.info(f"Processing schedule for user {user.email}, bin type: {schedule.bin_type}")

                # Determine which notification preferences to use
                if notification_time == 'evening':
                    should_notify = user.evening_notification
                    notification_type = user.evening_notification_type
                    logger.info(f"Evening notification settings - enabled: {should_notify}, type: {notification_type}")
                else:
                    should_notify = user.morning_notification
                    notification_type = user.morning_notification_type
                    logger.info(f"Morning notification settings - enabled: {should_notify}, type: {notification_type}")

                if should_notify:
                    # Send email if configured
                    if notification_type in ['email', 'both']:
                        logger.info(f"Attempting to send email notification to {user.email}")
                        email_sent = send_collection_reminder(
                            user.email,
                            schedule.bin_type,
                            schedule.next_collection
                        )
                        notification_sent = notification_sent or email_sent
                        logger.info(f"Email notification {'sent successfully' if email_sent else 'failed'}")

                    # Send SMS if configured
                    if notification_type in ['sms', 'both']:
                        logger.info(f"Attempting to send SMS notification to {user.phone}")
                        sms_sent = send_sms_reminder(
                            user.phone,
                            schedule.bin_type,
                            schedule.next_collection,
                            user
                        )
                        notification_sent = notification_sent or sms_sent
                        logger.info(f"SMS notification {'sent successfully' if sms_sent else 'failed'}")

                    if notification_sent and notification_time == 'evening':
                        # Update next collection date based on frequency
                        try:
                            if schedule.frequency == 'weekly':
                                schedule.next_collection += timedelta(days=7)
                            else:  # biweekly
                                schedule.next_collection += timedelta(days=14)

                            db.session.commit()
                            logger.info(f"Updated next collection date to {schedule.next_collection}")
                        except Exception as e:
                            db.session.rollback()
                            logger.error(f"Failed to update next collection date: {str(e)}")

        except Exception as e:
            logger.error(f"Error in check_upcoming_collections: {str(e)}")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/')
def home():  # Changed function name from index to home
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('home.html')

@app.route('/dashboard')
@login_required
def dashboard():
    schedules = BinSchedule.query.filter_by(user_id=current_user.id).all()
    replit_slug = os.environ.get('REPLIT_SLUG', '')
    return render_template('dashboard.html', schedules=schedules, replit_slug=replit_slug)

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
    if send_test_sms(current_user.phone, current_user):
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

            # Redirect to first-login page for new users with postcode
            if user.first_login and user.postcode:
                return redirect(url_for('first_login'))

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
            postcode = request.form.get('postcode')  # Get postcode from form
            password = request.form.get('password')
            referral_code = request.args.get('ref')  # Get referral code from URL

            if User.query.filter_by(email=email).first():
                flash('Email already registered')
                return redirect(url_for('register'))

            if not validate_phone(phone):
                flash('Invalid phone number format. Please use a valid format (e.g., +1234567890)')
                return redirect(url_for('register'))

            # Create new user with default 6 credits and postcode
            user = User(email=email, phone=phone, postcode=postcode, sms_credits=6)
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
            # (This section needs 'mail' object, which is missing from the provided code)

            return redirect(url_for('login'))
        except Exception as e:
            logger.error(f"Error during registration: {str(e)}")
            flash('An error occurred during registration. Please try again.')
            db.session.rollback()

    return render_template('auth/register.html', referral_code=request.args.get('ref'))

@app.route('/first-login')
@login_required
def first_login():
    """Handle first-time login and schedule suggestions."""
    if not current_user.first_login:
        return redirect(url_for('dashboard'))

    try:
        # Get collection schedules for user's postcode
        schedules = {}
        postcode_schedules = PostcodeSchedule.query.filter_by(postcode=current_user.postcode).all()

        for bin_type in ['refuse', 'recycling', 'garden_waste']:
            schedule = next((s for s in postcode_schedules if s.bin_type == bin_type), None)
            if schedule:
                next_collection = PostcodeSchedule.get_next_collection(
                    schedule.collection_day,
                    schedule.last_collection,
                    schedule.frequency
                )
                schedules[bin_type] = {
                    'frequency': schedule.frequency,
                    'collection_day': schedule.collection_day,
                    'next_collection': next_collection
                }

        return render_template('first_login.html', schedules=schedules)
    except Exception as e:
        logger.error(f"Error loading first login page: {str(e)}")
        flash('Error loading collection schedules')
        return redirect(url_for('dashboard'))

@app.route('/confirm-schedules', methods=['POST'])
@login_required
def confirm_schedules():
    """Handle confirmation of suggested schedules."""
    try:
        for bin_type in ['refuse', 'recycling', 'garden_waste']:
            if request.form.get(f'accept_{bin_type}'):
                postcode_schedule = PostcodeSchedule.query.filter_by(
                    postcode=current_user.postcode,
                    bin_type=bin_type
                ).first()

                if postcode_schedule:
                    next_collection = PostcodeSchedule.get_next_collection(
                        postcode_schedule.collection_day,
                        postcode_schedule.last_collection,
                        postcode_schedule.frequency
                    )

                    schedule = BinSchedule(
                        user_id=current_user.id,
                        bin_type=bin_type,
                        frequency=postcode_schedule.frequency,
                        next_collection=next_collection
                    )
                    db.session.add(schedule)

        # Mark first login as complete
        current_user.first_login = False
        db.session.commit()
        flash('Collection schedules have been set up successfully')
    except Exception as e:
        logger.error(f"Error confirming schedules: {str(e)}")
        db.session.rollback()
        flash('Error setting up collection schedules')

    return redirect(url_for('dashboard'))

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

        # Set default values when notifications are disabled
        if not evening_notification:
            evening_notification_time = 18  # Default to 6 PM
            evening_notification_type = 'email'  # Default to email

        if not morning_notification:
            morning_notification_time = 8  # Default to 8 AM
            morning_notification_type = 'email'  # Default to email

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
        logger.info(f"Updated notification preferences for user {current_user.email}")
        logger.info(f"Evening: {evening_notification} at {evening_notification_time}:00 GMT ({evening_notification_type})")
        logger.info(f"Morning: {morning_notification} at {morning_notification_time}:00 GMT ({morning_notification_type})")

        # Update scheduler jobs with explicit GMT timezone
        scheduler.remove_all_jobs()
        gmt = pytz.timezone('GMT')

        # Add evening notification job if enabled
        if evening_notification:
            scheduler.add_job(
                check_upcoming_collections,
                'cron',
                hour=evening_notification_time,
                minute=0,
                timezone=gmt,
                id='evening_notifications',
                args=['evening'],
                replace_existing=True
            )
            logger.info(f"Added evening notification job at {evening_notification_time}:00 GMT")

        # Add morning notification job if enabled
        if morning_notification:
            scheduler.add_job(
                check_upcoming_collections,
                'cron',
                hour=morning_notification_time,
                minute=0,
                timezone=gmt,
                id='morning_notifications',
                args=['morning'],
                replace_existing=True
            )
            logger.info(f"Added morning notification job at {morning_notification_time}:00 GMT")

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


# Admin routes
@app.route('/admin')
@admin_required
def admin_dashboard():
    try:
        # Gather statistics
        total_users = User.query.count()
        total_schedules = BinSchedule.query.count()
        total_emails = EmailLog.query.count()
        failed_emails = EmailLog.query.filter_by(status='failure').count()
        total_credits = db.session.query(func.sum(User.sms_credits)).scalar() or 0
        total_referrals = db.session.query(func.count(User.referred_by_id)).filter(User.referred_by_id.isnot(None)).scalar()

        # Get collection statistics for the past week
        week_ago = datetime.now() - timedelta(days=7)
        collections_this_week = BinSchedule.query.filter(
            BinSchedule.next_collection >= week_ago
        ).count()

        return render_template('admin/dashboard.html',
                            total_users=total_users,
                            total_schedules=total_schedules,
                            total_emails=total_emails,
                            failed_emails=failed_emails,
                            total_credits=total_credits,
                            total_referrals=total_referrals,
                            collections_this_week=collections_this_week)
    except Exception as e:
        logger.error(f"Error in admin dashboard: {str(e)}")
        flash('Error loading dashboard data')
        return redirect(url_for('home'))

@app.route('/admin/templates')
@admin_required
def admin_templates():
    """View SMS templates."""
    try:
        templates = SMSTemplate.query.all()
        return render_template('admin/templates.html', templates=templates)
    except Exception as e:
        logger.error(f"Error loading SMS templates: {str(e)}")
        flash('Error loading templates')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/templates/create', methods=['POST'])
@admin_required
def create_template():
    """Create a new SMS template."""
    try:
        name = request.form.get('name')
        template_text = request.form.get('template_text')
        description = request.form.get('description')

        template = SMSTemplate(
            name=name,
            template_text=template_text,
            description=description
        )
        db.session.add(template)
        db.session.commit()

        logger.info(f"Created new SMS template: {name}")
        flash('Template created successfully')
    except Exception as e:
        logger.error(f"Error creating template: {str(e)}")
        db.session.rollback()
        flash('Error creating template')

    return redirect(url_for('admin_templates'))

@app.route('/admin/templates/<int:template_id>/update', methods=['POST'])
@admin_required
def update_template(template_id):
    """Update an existing SMS template."""
    try:
        template = SMSTemplate.query.get_or_404(template_id)
        template.name = request.form.get('name')
        template.template_text = request.form.get('template_text')
        template.description = request.form.get('description')

        db.session.commit()
        logger.info(f"Updated SMS template: {template.name}")
        flash('Template updated successfully')
    except Exception as e:
        logger.error(f"Error updating template: {str(e)}")
        db.session.rollback()
        flash('Error updating template')

    return redirect(url_for('admin_templates'))

@app.route('/admin/users')
@admin_required
def admin_users():
    try:
        users = User.query.all()
        return render_template('admin/users.html', users=users, environ=os.environ)
    except Exception as e:
        logger.error(f"Error loading users: {str(e)}")
        flash('Error loading user data')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/users/create', methods=['POST'])
@admin_required
def create_user():
    try:
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')
        is_admin = request.form.get('is_admin') == 'on'
        sms_credits = int(request.form.get('sms_credits', 6))

        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return redirect(url_for('admin_users'))

        user = User(email=email, phone=phone, is_admin=is_admin, sms_credits=sms_credits)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        logger.info(f"Admin created new user: {email}")
        flash('User created successfully')
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        db.session.rollback()
        flash('Error creating user')

    return redirect(url_for('admin_users'))

@app.route('/admin/reminders')
@admin_required
def admin_reminders():
    try:
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        schedules = BinSchedule.query.join(User).all()
        return render_template('admin/reminders.html', 
                            schedules=schedules,
                            today=today,
                            tomorrow=tomorrow)
    except Exception as e:
        logger.error(f"Error loading reminders: {str(e)}")
        flash('Error loading reminder data')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/emails')
@admin_required
def admin_email_logs():
    try:
        logs = EmailLog.query.order_by(EmailLog.sent_at.desc()).all()
        return render_template('admin/email_logs.html', logs=logs)
    except Exception as e:
        logger.error(f"Error loading email logs: {str(e)}")
        flash('Error loading email logs')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/sms')
@admin_required
def admin_sms_logs():
    try:
        logs = SMSLog.query.order_by(SMSLog.sent_at.desc()).all()
        return render_template('admin/sms_logs.html', logs=logs)
    except Exception as e:
        logger.error(f"Error loading SMS logs: {str(e)}")
        flash('Error loading SMS logs')
        return redirect(url_for('admin_dashboard'))

@app.route('/api/check-notifications', methods=['GET'])
def check_notifications():
    """
    Public endpoint to check and send overdue notifications.
    This endpoint does not require authentication.
    """
    try:
        gmt = pytz.timezone('GMT')
        current_time = datetime.now(gmt)

        notifications_sent = {
            'evening': 0,
            'morning': 0,
            'errors': 0
        }

        # Check evening notifications (for tomorrow's collections)
        evening_users = User.query.filter(
            User.evening_notification == True
        ).all()

        for user in evening_users:
            user_notification_time = current_time.replace(
                hour=user.evening_notification_time,
                minute=0,
                second=0,
                microsecond=0
            )

            if current_time > user_notification_time:
                try:
                    check_upcoming_collections('evening')
                    notifications_sent['evening'] += 1
                except Exception as e:
                    logger.error(f"Error sending evening notification: {str(e)}")
                    notifications_sent['errors'] += 1

        # Check morning notifications (for today's collections)
        morning_users = User.query.filter(
            User.morning_notification == True
        ).all()

        for user in morning_users:
            user_notification_time = current_time.replace(
                hour=user.morning_notification_time,
                minute=0,
                second=0,
                microsecond=0
            )

            if current_time > user_notification_time:
                try:
                    check_upcoming_collections('morning')
                    notifications_sent['morning'] += 1
                except Exception as e:
                    logger.error(f"Error sending morning notification: {str(e)}")
                    notifications_sent['errors'] += 1

        logger.info(f"Notifications sent: {notifications_sent}")
        return jsonify({
            'status': 'success',
            'timestamp': current_time.isoformat(),
            'notifications_sent': notifications_sent
        })

    except Exception as e:
        logger.error(f"Error in check_notifications endpoint: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

if __name__ == '__main__':
    # Start the scheduler
    scheduler.start()
    logger.info("Notification scheduler started")

    app.run(host='0.0.0.0', port=5000)