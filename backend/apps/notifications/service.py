"""
Notification service for creating and managing notifications.
"""
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)



def send_push_notification(user, title, body="", data=None, channel_id="airway_general"):
    """Send a high-priority Firebase push to registered devices, without
    allowing push delivery failures to interrupt booking or dispatch flows."""
    from apps.accounts.models import DeviceToken

    tokens = list(DeviceToken.objects.filter(user=user).values_list("token", flat=True))
    if not tokens:
        return 0

    try:
        from firebase_admin import messaging
        message = messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(title=title, body=body),
            data={str(key): str(value) for key, value in (data or {}).items() if value is not None},
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    channel_id=channel_id,
                    sound="default",
                    priority="max",
                    visibility="public",
                ),
            ),
            apns=messaging.APNSConfig(
                headers={"apns-priority": "10"},
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(sound="default"),
                ),
            ),
        )
        response = messaging.send_each_for_multicast(message)
        for index, result in enumerate(response.responses):
            if result.success:
                continue
            error_code = getattr(result.exception, "code", "")
            if error_code in (
                "messaging/registration-token-not-registered",
                "messaging/invalid-registration-token",
            ):
                DeviceToken.objects.filter(token=tokens[index]).delete()
        return response.success_count
    except Exception:
        logger.exception("Firebase push delivery failed for user %s", user.pk)
        return 0

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