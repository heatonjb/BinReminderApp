from flask import render_template, redirect, url_for, request, flash
from app import app, db
from models import User, BinSchedule, EmailLog
from decorators import admin_required
from sqlalchemy import func
from datetime import datetime, timedelta

@app.route('/admin')
@admin_required
def admin_dashboard():
    # Gather statistics
    total_users = User.query.count()
    total_schedules = BinSchedule.query.count()
    total_emails = EmailLog.query.count()
    failed_emails = EmailLog.query.filter_by(status='failure').count()
    
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
                         collections_this_week=collections_this_week)

@app.route('/admin/users')
@admin_required
def admin_users():
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/users/create', methods=['POST'])
@admin_required
def create_user():
    email = request.form.get('email')
    phone = request.form.get('phone')
    password = request.form.get('password')
    is_admin = request.form.get('is_admin') == 'on'
    
    if User.query.filter_by(email=email).first():
        flash('Email already registered')
        return redirect(url_for('admin_users'))
    
    user = User(email=email, phone=phone, is_admin=is_admin)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    
    flash('User created successfully')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/toggle_admin', methods=['POST'])
@admin_required
def toggle_admin(user_id):
    user = User.query.get_or_404(user_id)
    user.is_admin = not user.is_admin
    db.session.commit()
    flash(f'Admin status updated for {user.email}')
    return redirect(url_for('admin_users'))

@app.route('/admin/reminders')
@admin_required
def admin_reminders():
    from datetime import datetime, timedelta
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    schedules = BinSchedule.query.join(User).all()
    return render_template('admin/reminders.html', 
                         schedules=schedules,
                         today=today,
                         tomorrow=tomorrow)

@app.route('/admin/emails')
@admin_required
def admin_email_logs():
    logs = EmailLog.query.order_by(EmailLog.sent_at.desc()).all()
    return render_template('admin/email_logs.html', logs=logs)
