from flask import render_template, redirect, url_for, request, flash
from app import app, db
from models import User, BinSchedule, EmailLog
from decorators import admin_required
from sqlalchemy import func
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

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
        return redirect(url_for('index'))

@app.route('/admin/users')
@admin_required
def admin_users():
    try:
        users = User.query.all()
        return render_template('admin/users.html', users=users)
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

@app.route('/admin/users/<int:user_id>/update_credits', methods=['POST'])
@admin_required
def update_credits(user_id):
    try:
        user = User.query.get_or_404(user_id)
        new_credits = int(request.form.get('credits', 0))

        if new_credits < 0:
            flash('Credits cannot be negative')
            return redirect(url_for('admin_users'))

        user.sms_credits = new_credits
        db.session.commit()

        logger.info(f"Updated SMS credits for user {user.email} to {new_credits}")
        flash(f'SMS credits updated for {user.email}')
    except Exception as e:
        logger.error(f"Error updating SMS credits: {str(e)}")
        db.session.rollback()
        flash('Error updating SMS credits')

    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/toggle_admin', methods=['POST'])
@admin_required
def toggle_admin(user_id):
    try:
        user = User.query.get_or_404(user_id)
        user.is_admin = not user.is_admin
        db.session.commit()
        logger.info(f"Admin status toggled for user {user.email}")
        flash(f'Admin status updated for {user.email}')
    except Exception as e:
        logger.error(f"Error toggling admin status: {str(e)}")
        db.session.rollback()
        flash('Error updating admin status')

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