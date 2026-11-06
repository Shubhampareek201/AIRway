from rest_framework import serializers

from .models import (
    WorkerProfile,
    WorkerDocument,
    WorkerService,
    WorkerZone,
    WorkerSchedule,
    WorkerLeave,
    WorkerJobStreak,
)


class WorkerProfileSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()
    name = serializers.CharField(source="user.name", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)

    class Meta:
        model = WorkerProfile
        fields = [
            "id",
            "name",
            "phone",
            "status",
            "is_online",
            "rating_avg",
            "experience_years",
            "upi_id",
            "photo_url",
        ]

    def get_photo_url(self, obj):
        if obj.status != WorkerProfile.Status.APPROVED:
            return None
        photo = obj.documents.filter(
            doc_type=WorkerDocument.DocumentType.PHOTO,
            status=WorkerDocument.Status.VERIFIED,
        ).first()
        if photo is None:
            return None
        try:
            return photo.file.url
        except Exception:
            return None


class WorkerProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkerProfile
        fields = [
            "experience_years",
            "bio",
            "upi_id",
        ]


class WorkerDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkerDocument
        fields = ["id", "doc_type", "status", "created_at"]


class WorkerServiceSerializer(serializers.ModelSerializer):
    service_title = serializers.CharField(source="service.title", read_only=True)

    class Meta:
        model = WorkerService
        fields = ["id", "service", "service_title"]


class WorkerZoneSerializer(serializers.ModelSerializer):
    zone_name = serializers.CharField(source="zone.name", read_only=True)

    class Meta:
        model = WorkerZone
        fields = ["id", "zone", "zone_name"]


class WorkerScheduleSerializer(serializers.ModelSerializer):
    weekday_display = serializers.CharField(source="get_weekday_display", read_only=True)

    class Meta:
        model = WorkerSchedule
        fields = ["id", "weekday", "weekday_display", "start_time", "end_time", "is_active"]


class WorkerLeaveSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkerLeave
        fields = ["id", "start_at", "end_at", "reason"]


class WorkerJobStreakSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkerJobStreak
        fields = ["id", "jobs_completed", "bonus_amount", "awarded_at"]