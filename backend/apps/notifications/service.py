"""
Notification service for creating and managing notifications.
"""
import logging
from datetime import timedelta
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
        from apps.accounts.firebase_service import get_firebase_app
        get_firebase_app()
        from firebase_admin import messaging
        payload = data or {}
        push_ttl = timedelta(minutes=10)
        if channel_id == "airway_job_alerts":
            # Never deliver a stale job alert after the service has started.
            scheduled_at = payload.get("scheduled_at")
            try:
                from datetime import datetime
                from django.utils import timezone as django_timezone
                scheduled = datetime.fromisoformat(str(scheduled_at).replace("Z", "+00:00"))
                if django_timezone.is_naive(scheduled):
                    scheduled = django_timezone.make_aware(scheduled)
                push_ttl = max(scheduled - django_timezone.now(), timedelta(seconds=0))
            except (TypeError, ValueError):
                push_ttl = timedelta(minutes=10)
        offer_tag = str(payload.get("offer_id") or "") or None
        message = messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(title=title, body=body),
            data={str(key): str(value) for key, value in payload.items() if value is not None},
            android=messaging.AndroidConfig(
                priority="high",
                ttl=push_ttl,
                notification=messaging.AndroidNotification(
                    channel_id=channel_id,
                    sound="default",
                    priority="max",
                    visibility="public",
                    tag=offer_tag,
                ),
            ),
            apns=messaging.APNSConfig(
                headers={
                    "apns-priority": "10",
                    **({"apns-collapse-id": offer_tag} if offer_tag else {}),
                },
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