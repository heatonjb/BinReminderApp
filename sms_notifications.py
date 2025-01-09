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
    telnyx.api_key = api_key
    return telnyx

def send_sms_reminder(to_phone_number: str, bin_type: str, collection_date, user) -> bool:
    """Send SMS reminder with error handling, logging, and credit check."""
    try:
        # Check if user has SMS credits
        if not user.has_sms_credits():
            logger.warning(f"User {user.email} has no SMS credits remaining")
            return False

        telnyx_client = get_telnyx_client()
        if not telnyx_client:
            raise ValueError("Telnyx API key not configured")

        # Create invite URL
        invite_url = f"https://{os.environ.get('REPLIT_SLUG')}.repl.co/register?ref={user.referral_code}"

        # Compose message with referral information
        message_text = (
            f"Reminder: Your {bin_type} bin collection is scheduled for tomorrow, "
            f"{collection_date.strftime('%A, %B %d, %Y')}. Please ensure your bin is "
            f"placed outside before collection time.\n\n"
            f"Invite friends to get more SMS credits! Share your link: {invite_url}"
        )

        message = telnyx.Message.create(
            from_=os.environ.get("TELNYX_MESSAGING_PROFILE_ID"),
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
            raise ValueError("Telnyx API key not configured")

        # Create invite URL
        invite_url = f"https://{os.environ.get('REPLIT_SLUG')}.repl.co/register?ref={user.referral_code}"

        message_text = (
            "Test message from your Bin Collection Reminder Service. "
            "SMS notifications are working correctly.\n\n"
            f"Invite friends to get more SMS credits! Share your link: {invite_url}"
        )

        message = telnyx.Message.create(
            from_=os.environ.get("TELNYX_MESSAGING_PROFILE_ID"),
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