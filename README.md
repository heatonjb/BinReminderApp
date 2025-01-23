# Bins Out - Never miss a bin or recyling day again

A refuse reminder platform that optimizes bin collection services

## Features

- Postcode-based scheduling
- Admin user management
- Credit tracking system
- Referral system
- GMT-synchronized SMS notifications
- Sustainability monitoring
- Time zone aware notifications
- Comprehensive SMS logs
- Email notifications

## Tech Stack

- Backend: Flask
- Database: PostgreSQL
- Frontend: Vanilla JavaScript
- Communication: Twilio, Telnyx SMS APIs, MailerSend Email
- Notification System: Cron-triggered API endpoint

## Setup

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up environment variables:
   - `DATABASE_URL`: PostgreSQL database URL
   - `MAILERSEND_API_KEY`: MailerSend API key
   - `MAILERSEND_FROM_EMAIL`: Sender email for MailerSend
   - `NOTIFICATION_API_KEY`: API key for SMS notifications

4. Initialize the database:
   ```bash
   flask db upgrade
   ```

5. Run the application:
   ```bash
   python main.py
   ```

## License

This project is proprietary and confidential.
