from django.urls import path

from . import admin_dashboard as views

app_name = "admin_dashboard"

urlpatterns = [
    path("login/", views.admin_login, name="login"),
    path("logout/", views.admin_logout, name="logout"),
    path("", views.dashboard, name="dashboard"),
    path("applications/", views.applications, name="applications"),
    path("professionals/", views.professionals, name="professionals"),
    path("customers/", views.customers, name="customers"),
    path("bookings/", views.bookings, name="bookings"),
    path("orders/", views.orders, name="orders"),
    path("payments/", views.payments, name="payments"),
    path("catalogue/", views.catalogue, name="catalogue"),
    path("activity/", views.activity, name="activity"),
    path("applications/<int:worker_id>/", views.application_detail, name="application_detail"),
    path("professionals/<int:worker_id>/status/", views.update_professional_status, name="update_professional_status"),
    path("applications/<int:worker_id>/documents/<int:document_id>/", views.review_document, name="review_document"),
    path("applications/<int:worker_id>/approve/", views.approve_application, name="approve_application"),
    path("applications/<int:worker_id>/reject/", views.reject_application, name="reject_application"),
]
