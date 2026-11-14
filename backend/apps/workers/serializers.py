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
    services = serializers.SerializerMethodField()
    zones = serializers.SerializerMethodField()
    schedules = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()
    name = serializers.CharField(source="user.name", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)

    class Meta:
        model = WorkerProfile
        fields = [
            "id",
            "name",
            "phone",
            "status",
            "gender",
            "is_online",
            "rejection_reason",
            "rating_avg",
            "experience_years",
            "qualification",
            "equipment_details",
            "residential_address",
            "latitude",
            "longitude",
            "landmark",
            "bio",
            "upi_id",
            "photo_url",
            "services",
            "zones",
            "schedules",
            "documents",
        ]

    def get_services(self, obj):
        return WorkerServiceSerializer(
            obj.worker_services.select_related("service", "service__category"),
            many=True,
        ).data

    def get_zones(self, obj):
        return WorkerZoneSerializer(
            obj.worker_zones.select_related("zone", "zone__city"),
            many=True,
        ).data

    def get_schedules(self, obj):
        return WorkerScheduleSerializer(
            obj.schedules.filter(is_active=True),
            many=True,
        ).data

    def get_documents(self, obj):
        return WorkerDocumentSerializer(obj.documents.all(), many=True).data

    def get_photo_url(self, obj):
        if obj.status != WorkerProfile.Status.APPROVED:
            return None
        photo = obj.documents.filter(
            doc_type=WorkerDocument.DocumentType.PHOTO,
            status=WorkerDocument.Status.VERIFIED,
        ).order_by("-created_at", "-id").first()
        if photo is None:
            return None
        try:
            return photo.file.url
        except Exception:
            return None


class WorkerProfileUpdateSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="user.name", required=False, allow_blank=False, max_length=150)

    class Meta:
        model = WorkerProfile
        fields = [
            "name",
            "experience_years",
            "bio",
            "qualification",
            "equipment_details",
            "residential_address",
            "latitude",
            "longitude",
            "landmark",
            "upi_id",
        ]

    def update(self, instance, validated_data):
        user_data = validated_data.pop("user", {})
        if "name" in user_data:
            instance.user.name = user_data["name"].strip()
            instance.user.save(update_fields=["name", "updated_at"])
        return super().update(instance, validated_data)


class WorkerDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkerDocument
        fields = ["id", "doc_type", "status", "created_at"]


class WorkerServiceSerializer(serializers.ModelSerializer):
    service_title = serializers.CharField(source="service.title", read_only=True)

    class Meta:
        model = WorkerService
        fields = ["id", "service", "service_title", "capabilities", "capabilities_verified", "experience_years"]


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