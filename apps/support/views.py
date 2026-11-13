from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.notifications.models import Notification
from .models import SupportTicket, SupportMessage
from .serializers import SupportTicketSerializer, SupportTicketCreateSerializer, SupportMessageSerializer

def notify(user, title, body, ticket, message):
    Notification.objects.create(user=user, type=Notification.Type.SYSTEM_ANNOUNCEMENT, title=title, body=body[:500], channel=Notification.Channel.IN_APP, data={"support_ticket_id":ticket.pk,"ticket_number":ticket.ticket_number,"support_message_id":message.pk})

class TicketListCreate(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    def get_queryset(self):
        return SupportTicket.objects.filter(user=self.request.user).prefetch_related("messages").order_by("-last_message_at")
    def get_serializer_class(self):
        return SupportTicketCreateSerializer if self.request.method == "POST" else SupportTicketSerializer
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data); s.is_valid(raise_exception=True)
        data = s.validated_data; text = data.pop("message"); attachment = data.pop("attachment", None)
        ticket = SupportTicket.objects.create(user=request.user, **data)
        msg = SupportMessage.objects.create(ticket=ticket, sender=request.user, message=text, attachment=attachment)
        ticket.last_message_at = msg.created_at; ticket.save(update_fields=["last_message_at","updated_at"])
        for admin in get_user_model().objects.filter(is_active=True, is_staff=True):
            notify(admin, f"New support request {ticket.ticket_number}", f"{ticket.subject}: {text}", ticket, msg)
        return Response(SupportTicketSerializer(ticket, context={"request":request}).data, status=201)

class TicketDetail(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    def ticket(self, request, pk):
        obj = SupportTicket.objects.filter(pk=pk).prefetch_related("messages__sender").first()
        if obj and obj.user_id != request.user.id and not request.user.is_staff: raise PermissionDenied()
        return obj
    def get(self, request, pk):
        obj = self.ticket(request, pk)
        if not obj: return Response({"detail":"Support ticket not found."}, status=404)
        rows = obj.messages.all() if request.user.is_staff else obj.messages.filter(is_internal_note=False)
        data = SupportTicketSerializer(obj, context={"request":request}).data
        data["messages"] = SupportMessageSerializer(rows.select_related("sender"), many=True, context={"request":request}).data
        return Response(data)
    @transaction.atomic
    def post(self, request, pk):
        obj = self.ticket(request, pk)
        if not obj: return Response({"detail":"Support ticket not found."}, status=404)
        if obj.status in (SupportTicket.Status.RESOLVED, SupportTicket.Status.CLOSED): return Response({"detail":"Ticket is closed. Create a new request."}, status=409)
        text = str(request.data.get("message","")).strip()
        if len(text)<5 or len(text)>5000: raise ValidationError({"message":"Message must contain 5 to 5000 characters."})
        attachment = request.FILES.get("attachment")
        if attachment and attachment.size > 10*1024*1024: raise ValidationError({"attachment":"Attachment must be 10 MB or smaller."})
        msg = SupportMessage.objects.create(ticket=obj, sender=request.user, message=text, attachment=attachment)
        obj.last_message_at = timezone.now()
        if request.user.is_staff:
            obj.status = SupportTicket.Status.WAITING_CUSTOMER
            notify(obj.user, "AIRway Support replied", f"{obj.ticket_number}: {text}", obj, msg)
        else:
            obj.status = SupportTicket.Status.IN_PROGRESS
            for admin in get_user_model().objects.filter(is_active=True, is_staff=True):
                notify(admin, f"Reply on {obj.ticket_number}", text, obj, msg)
        obj.save(update_fields=["last_message_at","status","updated_at"])
        return Response(SupportMessageSerializer(msg, context={"request":request}).data, status=201)

class AdminTicketList(generics.ListAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = SupportTicketSerializer
    def get_queryset(self):
        qs = SupportTicket.objects.all().select_related("user","assigned_to").prefetch_related("messages")
        state = self.request.query_params.get("status")
        category = self.request.query_params.get("category")
        if state in SupportTicket.Status.values: qs = qs.filter(status=state)
        if category in SupportTicket.Category.values: qs = qs.filter(category=category)
        return qs.order_by("-last_message_at")

class AdminTicketUpdate(APIView):
    permission_classes = [permissions.IsAdminUser]
    def patch(self, request, pk):
        obj = SupportTicket.objects.filter(pk=pk).first()
        if not obj: return Response({"detail":"Ticket not found."}, status=404)
        state = request.data.get("status")
        if state and state not in SupportTicket.Status.values: raise ValidationError({"status":"Invalid status."})
        if state: obj.status = state
        if "assigned_to" in request.data:
            uid = request.data.get("assigned_to")
            obj.assigned_to = get_user_model().objects.filter(pk=uid, is_staff=True).first() if uid else None
        obj.save(update_fields=["status","assigned_to","updated_at"])
        return Response(SupportTicketSerializer(obj, context={"request":request}).data)
