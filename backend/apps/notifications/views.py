from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Notification


class NotificationViewSet(viewsets.ModelViewSet):
    """
    Notification API endpoints.
    Users can list their notifications and mark them as read.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        from .serializers import NotificationSerializer as NS
        return NS

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None):
        """Mark a notification as read."""
        notification = self.get_object()
        if notification.user != request.user:
            return Response(
                {"detail": "Cannot mark another user's notification as read."},
                status=status.HTTP_403_FORBIDDEN
            )

        notification.mark_read()
        return Response({"detail": "Notification marked as read.", "is_read": True})

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request, pk=None):
        """Mark all unread notifications as read."""
        notifications = Notification.objects.filter(
            user=request.user,
            is_read=False
        )
        count = notifications.count()
        now = timezone.now()
        for notification in notifications:
            notification.read_at = now
            notification.is_read = True
            notification.save()

        return Response({
            "detail": f"{count} notifications marked as read.",
            "count": count
        })
