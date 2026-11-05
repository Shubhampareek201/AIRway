from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source="get_type_display", read_only=True)
    channel_display = serializers.CharField(source="get_channel_display", read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id", "type", "type_display", "title", "body",
            "channel", "channel_display", "is_read", "read_at",
            "created_at", "data"
        ]
        read_only_fields = ["data", "read_at", "created_at"]