"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('blog/', Home.as_view(), name='blog')
Including another URLconf
    Import the include() function: from django.urls import include, path
    Include another URLconf:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/workers/", include("apps.workers.urls")),
    path("api/v1/catalog/", include("apps.catalog.urls")),
    path("api/v1/bookings/", include("apps.bookings.urls")),
    path("api/v1/payments/", include("apps.payments.urls")),
    path("api/v1/notifications/", include("apps.notifications.urls")),
    path("api/v1/wallet/", include("apps.wallet.urls")),
    path("api/v1/ratings/", include("apps.ratings.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
