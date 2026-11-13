from django.urls import path
from .views import TicketListCreate, TicketDetail, AdminTicketList, AdminTicketUpdate
urlpatterns = [
    path("tickets/", TicketListCreate.as_view(), name="support-ticket-list"),
    path("tickets/<int:pk>/", TicketDetail.as_view(), name="support-ticket-detail"),
    path("admin/tickets/", AdminTicketList.as_view(), name="support-admin-ticket-list"),
    path("admin/tickets/<int:pk>/", AdminTicketUpdate.as_view(), name="support-admin-ticket-update"),
]
