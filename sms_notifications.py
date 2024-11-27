import os
from twilio.rest import Client
import logging

logger = logging.getLogger(__name__)

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")

def send_sms_reminder(to_phone_number: str, bin_type: str, collection_date) -> bool:
    """Send SMS reminder with error handling and logging."""
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        message = client.messages.create(
            body=f"Reminder: Your {bin_type} bin collection is scheduled for tomorrow, {collection_date.strftime('%A, %B %d, %Y')}. Please ensure your bin is placed outside before collection time.",
            from_=TWILIO_PHONE_NUMBER,
            to=to_phone_number
        )
        
        logger.info(f"Successfully sent SMS reminder to {to_phone_number} (SID: {message.sid})")
        return True
    except Exception as e:
        logger.error(f"Failed to send SMS reminder to {to_phone_number}: {str(e)}")
        return False

def send_test_sms(to_phone_number: str) -> bool:
    """Send a test SMS to verify Twilio configuration."""
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        message = client.messages.create(
            body="Test message from your Bin Collection Reminder Service. If you received this message, SMS notifications are working correctly.",
            from_=TWILIO_PHONE_NUMBER,
            to=to_phone_number
        )
        
        logger.info(f"Successfully sent test SMS to {to_phone_number} (SID: {message.sid})")
        return True
    except Exception as e:
        logger.error(f"Failed to send test SMS: {str(e)}")
        return False
