from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(ModelAdmin):
    list_display = ("user", "type", "title", "channel", "is_read", "created_at")
    list_filter = ("is_read", "channel", "type")
    search_fields = ("user__phone", "title")
    readonly_fields = ("created_at", "updated_at")

    actions = ["mark_as_read", "mark_as_unread"]

    @admin.action(description="Mark selected notifications as read")
    def mark_as_read(self, request, queryset):
        count = queryset.update(is_read=True)
        self.message_user(request, f"{count} notification(s) marked as read.")

    @admin.action(description="Mark selected notifications as unread")
    def mark_as_unread(self, request, queryset):
        count = queryset.update(is_read=False)
        self.message_user(request, f"{count} notification(s) marked as unread.")