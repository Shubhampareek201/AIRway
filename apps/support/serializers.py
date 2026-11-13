from rest_framework import serializers
from .models import SupportTicket, SupportMessage

class SupportMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source="sender.name", read_only=True)
    sender_role = serializers.SerializerMethodField()
    attachment_url = serializers.SerializerMethodField()
    class Meta:
        model = SupportMessage
        fields = ["id", "sender_name", "sender_role", "message", "attachment_url", "created_at"]
    def get_sender_role(self, obj):
        if obj.sender.is_staff: return "support"
        return "worker" if hasattr(obj.sender, "worker_profile") else "customer"
    def get_attachment_url(self, obj):
        if not obj.attachment: return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.attachment.url) if request else obj.attachment.url

class SupportTicketSerializer(serializers.ModelSerializer):
    messages = serializers.SerializerMethodField()
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    class Meta:
        model = SupportTicket
        fields = ["id","ticket_number","category","category_display","subject","status","status_display","booking_id","created_at","updated_at","last_message_at","messages"]
    def get_messages(self, obj):
        rows = obj.messages.filter(is_internal_note=False).select_related("sender")
        return SupportMessageSerializer(rows, many=True, context=self.context).data

class SupportTicketCreateSerializer(serializers.ModelSerializer):
    message = serializers.CharField(max_length=5000, write_only=True)
    attachment = serializers.FileField(required=False, allow_null=True, write_only=True)
    class Meta:
        model = SupportTicket
        fields = ["category","subject","booking_id","message","attachment"]
    def validate_subject(self, value):
        value = value.strip()
        if len(value) < 4: raise serializers.ValidationError("Subject must contain at least 4 characters.")
        return value
    def validate_message(self, value):
        value = value.strip()
        if len(value) < 5: raise serializers.ValidationError("Please provide more detail.")
        return value
    def validate_attachment(self, value):
        if value and value.size > 10 * 1024 * 1024: raise serializers.ValidationError("Attachment must be 10 MB or smaller.")
        return value
