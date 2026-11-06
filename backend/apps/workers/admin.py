from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone
from django.template.response import TemplateResponse
from unfold.admin import ModelAdmin, TabularInline

from apps.accounts.models import UserRole

from .models import (
    WorkerProfile,
    WorkerDocument,
    WorkerService,
    WorkerZone,
    WorkerSchedule,
    WorkerLeave,
)


class WorkerServiceInline(TabularInline):
    model = WorkerService
    extra = 0
    autocomplete_fields = ["service"]


class WorkerZoneInline(TabularInline):
    model = WorkerZone
    extra = 0
    autocomplete_fields = ["zone"]


class WorkerScheduleInline(TabularInline):
    model = WorkerSchedule
    extra = 0


@admin.register(WorkerProfile)
class WorkerProfileAdmin(ModelAdmin):
    list_display = (
        "user",
        "status",
        "is_online",
        "experience_years",
        "rating_avg",
        "approved_at",
    )

    list_filter = ("status", "is_online", "gender")
    search_fields = ("user__phone", "user__name")
    readonly_fields = (
        "approved_by",
        "approved_at",
        "rating_avg",
        "rating_count",
        "acceptance_rate",
        "cancellation_count",
        "rejection_reason",
    )

    inlines = [
        WorkerServiceInline,
        WorkerZoneInline,
        WorkerScheduleInline,
    ]

    actions = ["approve_workers", "suspend_workers", "reject_workers"]

    def approve_workers(self, request, queryset):
        approved_count = 0
        skipped_count = 0

        for worker in queryset:
            documents = worker.documents.all()

            has_verified_id = documents.filter(
                doc_type__in=["aadhaar", "id"],
                status=WorkerDocument.Status.VERIFIED,
            ).exists()

            has_service = worker.worker_services.exists()
            has_zone = worker.worker_zones.exists()

            if not (has_verified_id and has_service and has_zone):
                skipped_count += 1
                continue

            with transaction.atomic():
                worker.status = WorkerProfile.Status.APPROVED
                worker.approved_by = request.user
                worker.approved_at = timezone.now()
                worker.rejection_reason = ""
                worker.save()

                UserRole.objects.get_or_create(
                    user=worker.user,
                    role=UserRole.Role.WORKER,
                )

                approved_count += 1

        if approved_count:
            self.message_user(
                request,
                f"{approved_count} worker(s) approved successfully.",
                messages.SUCCESS,
            )

        if skipped_count:
            self.message_user(
                request,
                f"{skipped_count} worker(s) skipped. "
                "Verified ID, service and zone are required.",
                messages.WARNING,
            )

    approve_workers.short_description = "Approve selected workers"

    def suspend_workers(self, request, queryset):
        count = 0

        for worker in queryset:
            worker.status = WorkerProfile.Status.SUSPENDED
            worker.is_online = False
            worker.save()
            count += 1

        self.message_user(
            request,
            f"{count} worker(s) suspended.",
            messages.SUCCESS,
        )

    suspend_workers.short_description = "Suspend selected workers"

    def reject_workers(self, request, queryset):
        """Reject workers with a required reason."""
        if 'do_reject_workers' in request.POST:
            rejection_reason = request.POST.get('rejection_reason', '').strip()

            if not rejection_reason:
                self.message_user(
                    request,
                    "Rejection requires a reason. Please provide a reason.",
                    messages.WARNING,
                )
                return

            rejected_count = 0
            updated_ids = list(queryset.values_list('id', flat=True))

            with transaction.atomic():
                for worker_id in updated_ids:
                    try:
                        worker = WorkerProfile.objects.get(id=worker_id)
                        worker.status = WorkerProfile.Status.REJECTED
                        worker.rejection_reason = rejection_reason
                        worker.is_online = False
                        worker.save()
                        rejected_count += 1
                    except WorkerProfile.DoesNotExist:
                        continue

            if rejected_count:
                self.message_user(
                    request,
                    f"{rejected_count} worker(s) rejected with reason.",
                    messages.SUCCESS,
                )
            return

        # Show confirmation page
        context = {
            'title': 'Confirm worker rejection',
            'objects': queryset,
            'count': queryset.count(),
            'action': 'reject_workers',
            'queryset_count': queryset.count(),
        }
        return TemplateResponse(
            request,
            'admin/workers/workerprofile/reject_workers.html',
            context,
        )

    reject_workers.short_description = "Reject selected workers"


@admin.register(WorkerDocument)
class WorkerDocumentAdmin(ModelAdmin):
    list_display = ("worker", "doc_type", "status", "verified_by")
    list_filter = ("doc_type", "status")
    search_fields = ("worker__user__phone",)
    readonly_fields = ("verified_by",)

    def save_model(self, request, obj, form, change):
        if obj.status == WorkerDocument.Status.VERIFIED:
            obj.verified_by = request.user
        else:
            obj.verified_by = None

        super().save_model(request, obj, form, change)


@admin.register(WorkerService)
class WorkerServiceAdmin(ModelAdmin):
    list_display = ("worker", "service")
    search_fields = ("worker__user__phone", "service__title")


@admin.register(WorkerZone)
class WorkerZoneAdmin(ModelAdmin):
    list_display = ("worker", "zone")
    search_fields = ("worker__user__phone", "zone__name")


@admin.register(WorkerSchedule)
class WorkerScheduleAdmin(ModelAdmin):
    list_display = (
        "worker",
        "weekday",
        "start_time",
        "end_time",
        "is_active",
    )
    list_filter = ("weekday", "is_active")


@admin.register(WorkerLeave)
class WorkerLeaveAdmin(ModelAdmin):
    list_display = ("worker", "start_at", "end_at")
    search_fields = ("worker__user__phone",)