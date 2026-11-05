"""
Notification service for creating and managing notifications.
"""
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)


def create_notification(user, type, title, body="", channel="in_app", data=None):
    """
    Create a Notification record.

    Args:
        user: The user to notify
        type: Notification.Type enum value (string)
        title: Notification title
        body: Notification body text
        channel: Notification.Channel enum value (default: in_app)
        data: JSON-serializable dict with extra payload

    Returns:
        Notification instance
    """
    from apps.notifications.models import Notification

    notification = Notification.objects.create(
        user=user,
        type=type,
        title=title,
        body=body,
        channel=channel,
        data=data or {},
    )

    if channel in ("push", "sms", "email"):
        # Stubbed: log intent, do not deliver until gateway configured
        logger.info(f"[{channel.upper()}] Notification queued for user {user.pk}: {title}")

    return notification