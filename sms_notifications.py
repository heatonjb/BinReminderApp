import os
import telnyx
import logging
from app import db
from flask import url_for

logger = logging.getLogger(__name__)

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

        # Create invite URL
        invite_url = url_for('register', ref=user.referral_code, _external=True)

        # Compose message with referral information
        message_text = (
            f"Reminder: Your {bin_type} bin collection is scheduled for tomorrow, "
            f"{collection_date.strftime('%A, %B %d, %Y')}. Please ensure your bin is "
            f"placed outside before collection time.\n\n"
            f"Invite friends to get more SMS credits! Share your link: {invite_url}"
        )

        logger.info(f"Attempting to send SMS to {to_phone_number}")
        message = telnyx_client.Message.create(
            from_=os.environ.get("TELNYX_PHONE_NUMBER"),  # Changed from TELNYX_MESSAGING_PROFILE_ID to TELNYX_PHONE_NUMBER
            to=to_phone_number,
            text=message_text
        )

        # Deduct SMS credit
        user.use_sms_credit()
        db.session.commit()

        logger.info(f"Successfully sent SMS reminder to {to_phone_number} (ID: {message.id})")
        return True
    except Exception as e:
        logger.error(f"Failed to send SMS reminder to {to_phone_number}: {str(e)}")
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

        # Create invite URL using Flask's url_for
        invite_url = url_for('register', ref=user.referral_code, _external=True)

        message_text = (
            "Test message from your Bin Collection Reminder Service. "
            "SMS notifications are working correctly.\n\n"
            f"Invite friends to get more SMS credits! Share your link: {invite_url}"
        )

        logger.info(f"Attempting to send test SMS to {to_phone_number}")
        message = telnyx_client.Message.create(
            from_=os.environ.get("TELNYX_PHONE_NUMBER"),  # Changed from TELNYX_MESSAGING_PROFILE_ID to TELNYX_PHONE_NUMBER
            to=to_phone_number,
            text=message_text
        )

        # Deduct SMS credit
        user.use_sms_credit()
        db.session.commit()

        logger.info(f"Successfully sent test SMS to {to_phone_number} (ID: {message.id})")
        return True
    except Exception as e:
        logger.error(f"Failed to send test SMS: {str(e)}")
        return False