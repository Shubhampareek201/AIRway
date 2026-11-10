from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    NearbyWorkersView,
    WorkerProfileView,
    WorkerServiceListView,
    WorkerServiceDetailView,
    WorkerZoneListView,
    WorkerZoneDetailView,
    WorkerScheduleListView,
    WorkerScheduleDetailView,
    WorkerOnboardingView,
    WorkerJobListView,
    WorkerJobDetailView,
    WorkerJobAcceptView,
    WorkerJobRejectView,
    WorkerJobUnavailableView,
    WorkerJobStartView,
    WorkerJobCompleteView,
    WorkerDocumentUploadView,
    WorkerDocumentListView,
    WorkerEarningsView,
    WorkerStreaksView,
    WorkerStatusUpdateView,
    WorkerOfferViewSet,
)

router = DefaultRouter()
router.register(r"offers", WorkerOfferViewSet, basename="worker-offer")

app_name = "workers"

urlpatterns = [
    path("nearby/", NearbyWorkersView.as_view(), name="nearby-workers"),
    path("me/", WorkerProfileView.as_view(), name="worker-profile"),
    path("onboarding/", WorkerOnboardingView.as_view(), name="worker-onboarding"),
    path("apply/", WorkerOnboardingView.as_view(), name="worker-apply"),
    path("services/", WorkerServiceListView.as_view(), name="worker-services"),
    path("services/<int:service_id>/", WorkerServiceDetailView.as_view(), name="worker-service-detail"),
    path("zones/", WorkerZoneListView.as_view(), name="worker-zones"),
    path("zones/<int:zone_id>/", WorkerZoneDetailView.as_view(), name="worker-zone-detail"),
    path("schedules/", WorkerScheduleListView.as_view(), name="worker-schedules"),
    path("schedules/<int:schedule_id>/", WorkerScheduleDetailView.as_view(), name="worker-schedule-detail"),
    path("documents/upload/", WorkerDocumentUploadView.as_view(), name="worker-document-upload"),
    path("documents/", WorkerDocumentListView.as_view(), name="worker-document-list"),
    path("jobs/", WorkerJobListView.as_view(), name="worker-jobs"),
    path("jobs/<int:job_id>/", WorkerJobDetailView.as_view(), name="worker-job-detail"),
    path("jobs/<int:job_id>/accept/", WorkerJobAcceptView.as_view(), name="worker-job-accept"),
    path("jobs/<int:job_id>/reject/", WorkerJobRejectView.as_view(), name="worker-job-reject"),
    path("jobs/<int:job_id>/unavailable/", WorkerJobUnavailableView.as_view(), name="worker-job-unavailable"),
    path("jobs/<int:job_id>/start/", WorkerJobStartView.as_view(), name="worker-job-start"),
    path("jobs/<int:job_id>/complete/", WorkerJobCompleteView.as_view(), name="worker-job-complete"),
    path("earnings/", WorkerEarningsView.as_view(), name="worker-earnings"),
    path("streaks/", WorkerStreaksView.as_view(), name="worker-streaks"),
    path("status/", WorkerStatusUpdateView.as_view(), name="worker-status"),
    path("", include(router.urls)),
]