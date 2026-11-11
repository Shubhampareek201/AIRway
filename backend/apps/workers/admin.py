from django.contrib import admin, messages
from django.db.models import Case, IntegerField, Value, When
from django.template.response import TemplateResponse
from unfold.admin import ModelAdmin, TabularInline


from .approval import approve_worker, get_approval_requirements

from .models import (
    WorkerProfile,
    WorkerDocument,
    WorkerService,
    WorkerZone,
    WorkerSchedule,
    WorkerLeave,
)


class WorkerDocumentInline(TabularInline):
    """Review uploaded identity documents and photos from the application itself."""

    model = WorkerDocument
    extra = 0
    fields = ("doc_type", "file", "status", "verified_by", "created_at")
    readonly_fields = ("file", "verified_by", "created_at")
    can_delete = False
    show_change_link = True


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
        "worker_name",
        "worker_phone",
        "status",
        "document_summary",
        "service_summary",
        "zone_summary",
        "created_at",
    )
    list_display_links = ("worker_name", "worker_phone")
    list_filter = ("status", "gender", "created_at")
    search_fields = ("user__phone", "user__name", "user__email")
    date_hierarchy = "created_at"
    list_per_page = 25
    save_on_top = True
    ordering = ("-created_at",)
    readonly_fields = (
        "approved_by",
        "approved_at",
        "rating_avg",
        "rating_count",
        "acceptance_rate",
        "cancellation_count",
    )
    fieldsets = (
        ("Worker account", {"fields": ("user", "status", "gender")}),
        ("Application details", {"fields": (
            "experience_years", "qualification", "equipment_details",
            "residential_address", "landmark", "bio", "upi_id",
        )}),
        ("Review decision", {"fields": ("rejection_reason", "approved_by", "approved_at")}),
        ("Performance (read only)", {
            "fields": ("is_online", "rating_avg", "rating_count", "acceptance_rate", "cancellation_count"),
        }),
    )
    inlines = [
        WorkerDocumentInline,
        WorkerServiceInline,
        WorkerZoneInline,
        WorkerScheduleInline,
    ]
    actions = ["approve_workers", "suspend_workers", "reject_workers"]

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related("user").prefetch_related(
            "documents",
            "worker_services__service",
            "worker_zones__zone",
        )
        # Keep applications needing attention at the top of the queue.
        return queryset.annotate(
            pending_order=Case(
                When(status=WorkerProfile.Status.PENDING, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by("pending_order", "-created_at")

    @admin.display(description="Worker", ordering="user__name")
    def worker_name(self, obj):
        return obj.user.name or "Name not provided"

    @admin.display(description="Phone", ordering="user__phone")
    def worker_phone(self, obj):
        return obj.user.phone or "—"

    @admin.display(description="Documents")
    def document_summary(self, obj):
        docs = list(obj.documents.all())
        verified_ids = sum(
            1 for doc in docs
            if doc.doc_type in (WorkerDocument.DocumentType.AADHAAR, WorkerDocument.DocumentType.ID)
            and doc.status == WorkerDocument.Status.VERIFIED
        )
        pending = sum(1 for doc in docs if doc.status == WorkerDocument.Status.PENDING)
        return f"{verified_ids} verified ID(s) · {pending} pending"

    @admin.display(description="Services")
    def service_summary(self, obj):
        titles = [link.service.title for link in obj.worker_services.all()]
        return ", ".join(titles) if titles else "Not added"

    @admin.display(description="Zones")
    def zone_summary(self, obj):
        names = [link.zone.name for link in obj.worker_zones.all()]
        return ", ".join(names) if names else "Not added"

    def save_model(self, request, obj, form, change):
        previous_status = None
        if change:
            previous_status = (
                WorkerProfile.objects
                .filter(pk=obj.pk)
                .values_list("status", flat=True)
                .first()
            )

        approval_requested = (
            change
            and obj.status == WorkerProfile.Status.APPROVED
            and previous_status == WorkerProfile.Status.PENDING
        )

        if obj.status == WorkerProfile.Status.APPROVED and approval_requested:
            # Inline documents/services/zones/schedules are saved after save_model.
            # Keep the row pending until save_related can validate the saved inlines.
            obj.status = WorkerProfile.Status.PENDING
            obj.is_online = False
        elif (
            obj.status == WorkerProfile.Status.APPROVED
            and previous_status != WorkerProfile.Status.APPROVED
        ):
            obj.status = (
                previous_status
                if previous_status is not None
                else WorkerProfile.Status.PENDING
            )
            obj.is_online = False
            self.message_user(
                request,
                "Only an existing pending worker application can be approved.",
                messages.WARNING,
            )

        super().save_model(request, obj, form, change)

        if approval_requested:
            request._worker_approval_requested = True
            request._worker_approval_worker_id = obj.pk

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for deleted_object in formset.deleted_objects:
            deleted_object.delete()

        for instance in instances:
            if isinstance(instance, WorkerDocument):
                instance.verified_by = (
                    request.user
                    if instance.status == WorkerDocument.Status.VERIFIED
                    else None
                )
            instance.save()

        formset.save_m2m()

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if not getattr(request, "_worker_approval_requested", False):
            return

        result = approve_worker(
            request._worker_approval_worker_id,
            request.user,
        )
        if result["status"] == "approved":
            worker = result["worker"]
            self.message_user(
                request,
                f"{worker.user.name or worker.user.phone} has been approved.",
                messages.SUCCESS,
            )
        elif result["status"] == "ineligible":
            missing = "; ".join(result["requirements"]["missing"])
            self.message_user(
                request,
                "Application saved as pending. Missing approval requirements: " + missing,
                messages.WARNING,
            )
        else:
            self.message_user(
                request,
                "This application could not be approved because its status changed.",
                messages.WARNING,
            )

    def approve_workers(self, request, queryset):
        approved_count = 0
        skipped_count = 0
        missing_requirements = set()

        for worker_id in queryset.values_list("pk", flat=True).iterator():
            result = approve_worker(worker_id, request.user)
            if result["status"] == "approved":
                approved_count += 1
            else:
                skipped_count += 1
                if result.get("requirements"):
                    missing_requirements.update(result["requirements"]["missing"])

        if approved_count:
            self.message_user(
                request,
                f"{approved_count} worker application(s) approved successfully.",
                messages.SUCCESS,
            )

        if skipped_count:
            detail = (
                " Missing requirements: " + "; ".join(sorted(missing_requirements))
                if missing_requirements else ""
            )
            self.message_user(
                request,
                f"{skipped_count} application(s) were not approved.{detail}",
                messages.WARNING,
            )

    approve_workers.short_description = "Approve selected pending applications"

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
        if "do_reject_workers" in request.POST:
            rejection_reason = request.POST.get("rejection_reason", "").strip()
            if not rejection_reason:
                self.message_user(
                    request,
                    "Rejection requires a reason. Please provide a reason.",
                    messages.WARNING,
                )
                return

            rejected_count = 0
            updated_ids = list(queryset.values_list("id", flat=True))

            with transaction.atomic():
                for worker_id in updated_ids:
                    worker = WorkerProfile.objects.filter(
                        id=worker_id,
                        status=WorkerProfile.Status.PENDING,
                    ).first()
                    if worker is None:
                        continue

                    worker.status = WorkerProfile.Status.REJECTED
                    worker.rejection_reason = rejection_reason
                    worker.is_online = False
                    worker.save()
                    rejected_count += 1

            if rejected_count:
                self.message_user(
                    request,
                    f"{rejected_count} pending application(s) rejected with reason.",
                    messages.SUCCESS,
                )
            return

        context = {
            "title": "Confirm worker rejection",
            "objects": queryset,
            "count": queryset.count(),
            "action": "reject_workers",
            "queryset_count": queryset.count(),
        }
        return TemplateResponse(
            request,
            "admin/workers/workerprofile/reject_workers.html",
            context,
        )

    reject_workers.short_description = "Reject selected pending applications"


@admin.register(WorkerDocument)
class WorkerDocumentAdmin(ModelAdmin):
    list_display = ("worker", "doc_type", "status", "verified_by", "created_at")
    list_filter = ("doc_type", "status")
    search_fields = ("worker__user__phone", "worker__user__name")
    readonly_fields = ("verified_by", "created_at", "updated_at")
    list_per_page = 25

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
    list_display = ("worker", "weekday", "start_time", "end_time", "is_active")
    list_filter = ("weekday", "is_active")


@admin.register(WorkerLeave)
class WorkerLeaveAdmin(ModelAdmin):
    list_display = ("worker", "start_at", "end_at")
    search_fields = ("worker__user__phone",)
