import os
import telnyx
import logging
from app import db
from flask import url_for
import re
from models import SMSTemplate

logger = logging.getLogger(__name__)

def format_phone_number(phone_number: str) -> str:
    """Format phone number to E.164 format (+[country code][number])."""
    # Remove any non-digit characters
    cleaned = re.sub(r'\D', '', phone_number)

    # If number starts with '0', assume UK number and replace with +44
    if cleaned.startswith('0'):
        cleaned = '44' + cleaned[1:]

    # If no country code (less than 11 digits), assume UK and add +44
    if len(cleaned) <= 10:
        cleaned = '44' + cleaned

    # Add + prefix if not present
    if not cleaned.startswith('+'):
        cleaned = '+' + cleaned

    return cleaned

def get_telnyx_client():
    """Initialize Telnyx client with API key."""
    api_key = os.environ.get("TELNYX_API_KEY")
    if not api_key:
        logger.error("Telnyx API key not found in environment variables")
        return None

    try:
        # Ensure we're using the API key correctly
        telnyx.api_key = api_key.strip()
        logger.info("Initialized Telnyx client with API key")
        return telnyx
    except Exception as e:
        logger.error(f"Failed to initialize Telnyx client: {str(e)}")
        return None

def get_message_from_template(template_name, **kwargs):
    """Get message text from a template."""
    try:
        template = SMSTemplate.query.filter_by(name=template_name, is_active=True).first()
        if template:
            return template.render(**kwargs)
    except Exception as e:
        logger.error(f"Error getting template '{template_name}': {str(e)}")
    return None

def send_sms_reminder(to_phone_number: str, bin_type: str, collection_date, user) -> bool:
    """Send SMS reminder with error handling, logging, and credit check."""
    try:
        # Check if user has SMS credits
        if not user.has_sms_credits():
            logger.warning(f"User {user.email} has no SMS credits remaining")
            return False

        telnyx_client = get_telnyx_client()
        if not telnyx_client:
            logger.error("Failed to initialize Telnyx client")
            return False

        # Format phone numbers
        formatted_to_number = format_phone_number(to_phone_number)
        source_number = format_phone_number(os.environ.get("TELNYX_PHONE_NUMBER", ""))

        logger.info(f"Formatted numbers - From: {source_number}, To: {formatted_to_number}")

        # Create invite URL
        invite_url = url_for('register', ref=user.referral_code, _external=True)

        # Get message from template or use default
        message_text = get_message_from_template('collection_reminder', 
            bin_type=bin_type,
            collection_date=collection_date.strftime('%A, %B %d, %Y'),
            invite_url=invite_url
        )

        if not message_text:
            # Fallback to default message if template not found
            message_text = (
                f"Reminder: Your {bin_type} bin collection is scheduled for tomorrow, "
                f"{collection_date.strftime('%A, %B %d, %Y')}. Please ensure your bin is "
                f"placed outside before collection time.\n\n"
                f"Invite friends to get more SMS credits! Share your link: {invite_url}"
            )

        logger.info(f"Attempting to send SMS from {source_number} to {formatted_to_number}")
        message = telnyx_client.Message.create(
            from_=source_number,
            to=formatted_to_number,
            text=message_text
        )

        # Deduct SMS credit
        user.use_sms_credit()
        db.session.commit()

        logger.info(f"Successfully sent SMS reminder to {formatted_to_number} (ID: {message.id})")
        return True
    except Exception as e:
        error_details = str(e)
        if hasattr(e, 'errors'):
            error_details = f"Full details: {e.errors}"
        logger.error(f"Failed to send SMS reminder to {to_phone_number}: {error_details}")
        return False

def send_test_sms(to_phone_number: str, user) -> bool:
    """Send a test SMS to verify Telnyx configuration."""
    try:
        # Check if user has SMS credits
        if not user.has_sms_credits():
            logger.warning(f"User {user.email} has no SMS credits remaining")
            return False

        telnyx_client = get_telnyx_client()
        if not telnyx_client:
            logger.error("Failed to initialize Telnyx client")
            return False

        # Format phone numbers
        formatted_to_number = format_phone_number(to_phone_number)
        source_number = format_phone_number(os.environ.get("TELNYX_PHONE_NUMBER", ""))

        logger.info(f"Formatted numbers - From: {source_number}, To: {formatted_to_number}")

        # Create invite URL using Flask's url_for
        invite_url = url_for('register', ref=user.referral_code, _external=True)

        # Get message from template or use default
        message_text = get_message_from_template('test_message',
            invite_url=invite_url
        )

        if not message_text:
            message_text = (
                "Test message from your Bin Collection Reminder Service. "
                "SMS notifications are working correctly.\n\n"
                f"Invite friends to get more SMS credits! Share your link: {invite_url}"
            )

        logger.info(f"Attempting to send test SMS from {source_number} to {formatted_to_number}")
        message = telnyx_client.Message.create(
            from_=source_number,
            to=formatted_to_number,
            text=message_text
        )

        # Deduct SMS credit
        user.use_sms_credit()
        db.session.commit()

        logger.info(f"Successfully sent test SMS to {formatted_to_number} (ID: {message.id})")
        return True
    except Exception as e:
        error_details = str(e)
        if hasattr(e, 'errors'):
            error_details = f"Full details: {e.errors}"
        logger.error(f"Failed to send test SMS: {error_details}")
        return False