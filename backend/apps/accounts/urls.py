
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    AddressDetailView,
    AddressListView,
    ChangePasswordView,
    CityListView,
    CurrentUserView,
    FirebaseLoginView,
    ForgotPasswordView,
    GeoapifyAutocompleteView,
    LocationReverseView,
    LocationSearchView,
    LoginView,
    ProfileCompletionView,
    RegisterView,
    ResetPasswordView,
    SetDefaultAddressView,
    VerifyForgotOTPView,
    ZoneListView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("profile-complete/", ProfileCompletionView.as_view(), name="profile-complete"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("forgot-password/", ForgotPasswordView.as_view(), name="forgot-password"),
    path("verify-otp/", VerifyForgotOTPView.as_view(), name="verify-otp"),
    path("reset-password/", ResetPasswordView.as_view(), name="reset-password"),
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
    path(
        "locations/reverse/",
        LocationReverseView.as_view(),
        name="location-reverse",
    ),
    path(
        "locations/autocomplete/",
        GeoapifyAutocompleteView.as_view(),
        name="location-autocomplete",
    ),
    path(
        "me/",
        CurrentUserView.as_view(),
        name="current-user",
    ),
    path(
        "cities/",
        CityListView.as_view(),
        name="city-list",
    ),
    path(
        "zones/",
        ZoneListView.as_view(),
        name="zone-list",
    ),
    path(
        "addresses/",
        AddressListView.as_view(),
        name="address-list",
    ),
    path(
        "addresses/<int:address_id>/set-default/",
        SetDefaultAddressView.as_view(),
        name="address-set-default",
    ),
    path(
        "addresses/<int:address_id>/",
        AddressDetailView.as_view(),
        name="address-detail",
    ),
    path(
        "locations/search/",
        LocationSearchView.as_view(),
        name="location-search",
    ),
]
