import os
import re
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from sqlalchemy.orm import DeclarativeBase
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or "a secret key"
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'login'

with app.app_context():
    import models
    db.create_all()

from models import User, BinSchedule

def validate_phone(phone):
    phone = re.sub(r'[-\s()]', '', phone)
    return bool(re.match(r'^\+?1?\d{10,12}$', phone))

def validate_date(date_str):
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d')
        return date >= datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    except ValueError:
        return False

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
@login_required
def dashboard():
    schedules = BinSchedule.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', schedules=schedules)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid email or password')
    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
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
    return render_template('auth/register.html')

@app.route('/schedule/update', methods=['POST'])
@login_required
def update_schedule():
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
    
    try:
        db.session.commit()
        flash(f'{bin_type.title()} bin schedule updated successfully')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while updating the schedule')
        
    return redirect(url_for('dashboard'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))
