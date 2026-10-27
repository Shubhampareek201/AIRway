
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import FirebaseLoginView

urlpatterns = [
    path(
        "firebase-login/",
        FirebaseLoginView.as_view(),
        name="firebase-login",
    ),
    path(
        "refresh/",
        TokenRefreshView.as_view(),
        name="token-refresh",
    ),
]
