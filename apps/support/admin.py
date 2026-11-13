from django.contrib import admin
from .models import SupportTicket, SupportMessage

class MessageInline(admin.TabularInline):
    model = SupportMessage
    extra = 0
    readonly_fields = ("sender","message","attachment","created_at")
    fields = ("sender","message","attachment","is_internal_note","created_at")

@admin.register(SupportTicket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("ticket_number","subject","user","category","status","assigned_to","last_message_at")
    list_filter = ("status","category","created_at")
    search_fields = ("ticket_number","subject","user__phone","user__name")
    readonly_fields = ("ticket_number","created_at","updated_at","last_message_at")
    inlines = [MessageInline]

@admin.register(SupportMessage)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("ticket","sender","is_internal_note","created_at")
    list_filter = ("is_internal_note","created_at")
    search_fields = ("ticket__ticket_number","message")
