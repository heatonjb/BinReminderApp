import os
import telnyx
import logging

logger = logging.getLogger(__name__)

def get_telnyx_client():
    """Initialize Telnyx client with API key."""
    api_key = os.environ.get("TELNYX_API_KEY")
    if not api_key:
        logger.error("Telnyx API key not found in environment variables")
        return None
    telnyx.api_key = api_key
    return telnyx

def send_sms_reminder(to_phone_number: str, bin_type: str, collection_date) -> bool:
    """Send SMS reminder with error handling and logging."""
    try:
        telnyx_client = get_telnyx_client()
        if not telnyx_client:
            raise ValueError("Telnyx API key not configured")

        message = telnyx.Message.create(
            from_=os.environ.get("TELNYX_MESSAGING_PROFILE_ID"),
            to=to_phone_number,
            text=f"Reminder: Your {bin_type} bin collection is scheduled for tomorrow, {collection_date.strftime('%A, %B %d, %Y')}. Please ensure your bin is placed outside before collection time."
        )

        logger.info(f"Successfully sent SMS reminder to {to_phone_number} (ID: {message.id})")
        return True
    except Exception as e:
        logger.error(f"Failed to send SMS reminder to {to_phone_number}: {str(e)}")
        return False

def send_test_sms(to_phone_number: str) -> bool:
    """Send a test SMS to verify Telnyx configuration."""
    try:
        telnyx_client = get_telnyx_client()
        if not telnyx_client:
            raise ValueError("Telnyx API key not configured")

        message = telnyx.Message.create(
            from_=os.environ.get("TELNYX_MESSAGING_PROFILE_ID"),
            to=to_phone_number,
            text="Test message from your Bin Collection Reminder Service. If you received this message, SMS notifications are working correctly."
        )

        logger.info(f"Successfully sent test SMS to {to_phone_number} (ID: {message.id})")
        return True
    except Exception as e:
        logger.error(f"Failed to send test SMS: {str(e)}")
        return False