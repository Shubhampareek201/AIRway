from django.urls import path

from .views import NearbyWorkersView

app_name = "workers"

urlpatterns = [
    path("nearby/", NearbyWorkersView.as_view(), name="nearby-workers"),
]
