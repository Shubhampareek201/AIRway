from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import transaction
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
    WorkerLeaveHistory,
    WorkerEarning,
    WorkerPayoutSettlement,
    WorkerRewardWallet,
    WorkerRewardTransaction,
    WorkerRewardWithdrawal,
    WorkerMonthlyMissionProgress,
    WorkerReferralSettings,
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
            "residential_address", "landmark", "bio", "upi_id", "commission_rate",
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

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser and not request.user.has_perm("workers.configure_worker_commission"):
            fields.append("commission_rate")
        return tuple(fields)

    def get_queryset(self, request):
        # Avoid prefetch_related here: Unfold's changelist processing uses
        # QuerySet.iterator() without chunk_size, which raises on prefetched
        # querysets under Django 6. Related summaries are intentionally loaded
        # per visible row; list_per_page keeps this bounded.
        queryset = super().get_queryset(request).select_related("user")
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
        previous_commission_rate = None
        if change:
            previous_commission_rate = (
                WorkerProfile.objects.filter(pk=obj.pk).values_list("commission_rate", flat=True).first()
            )
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
        suspension_or_rejection = (
            change
            and previous_status == WorkerProfile.Status.APPROVED
            and obj.status in (WorkerProfile.Status.SUSPENDED, WorkerProfile.Status.REJECTED)
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

        if change and previous_commission_rate != obj.commission_rate and obj.commission_rate is not None:
            from .earnings import refresh_worker_earnings_for_profile
            transaction.on_commit(
                lambda worker_id=obj.pk: refresh_worker_earnings_for_profile(worker_id)
            )

        if approval_requested:
            request._worker_approval_requested = True
            request._worker_approval_worker_id = obj.pk
        if suspension_or_rejection:
            from .dispatch_lifecycle import handle_worker_suspension
            transaction.on_commit(lambda worker_id=obj.pk: handle_worker_suspension(worker_id))

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
            from .dispatch_lifecycle import handle_worker_suspension
            handle_worker_suspension(worker.pk)
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


@admin.register(WorkerZoneChangeRequest)
class WorkerZoneChangeRequestAdmin(ModelAdmin):
    list_display = ("worker", "zone", "action", "status", "requested_at", "reviewed_by", "reviewed_at")
    list_filter = ("status", "action", "requested_at")
    search_fields = ("worker__user__phone", "worker__user__name", "zone__name")
    readonly_fields = ("worker", "zone", "action", "worker_note", "status", "requested_at", "reviewed_by", "reviewed_at")
    fields = ("worker", "zone", "action", "worker_note", "status", "admin_note", "requested_at", "reviewed_by", "reviewed_at")
    actions = ("approve_zone_requests", "reject_zone_requests")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Approve selected pending worker zone requests")
    def approve_zone_requests(self, request, queryset):
        from .zone_changes import review_worker_zone_change
        approved = skipped = 0
        for request_id in queryset.values_list("pk", flat=True):
            try:
                review_worker_zone_change(request_id=request_id, reviewer=request.user, decision=WorkerZoneChangeRequest.Status.APPROVED)
                approved += 1
            except Exception as exc:
                skipped += 1
                self.message_user(request, f"Zone request #{request_id} was not approved: {exc}", messages.WARNING)
        if approved:
            self.message_user(request, f"{approved} worker zone request(s) approved.", messages.SUCCESS)
        if skipped:
            self.message_user(request, f"{skipped} request(s) need attention.", messages.WARNING)

    @admin.action(description="Reject selected pending worker zone requests (add admin note first)")
    def reject_zone_requests(self, request, queryset):
        from .zone_changes import review_worker_zone_change
        rejected = skipped = 0
        for item in queryset:
            try:
                review_worker_zone_change(
                    request_id=item.pk, reviewer=request.user,
                    decision=WorkerZoneChangeRequest.Status.REJECTED, note=item.admin_note,
                )
                rejected += 1
            except Exception as exc:
                skipped += 1
                self.message_user(request, f"Zone request #{item.pk} was not rejected: {exc}", messages.WARNING)
        if rejected:
            self.message_user(request, f"{rejected} worker zone request(s) rejected.", messages.SUCCESS)
        if skipped:
            self.message_user(request, f"{skipped} request(s) skipped. Add a rejection note first.", messages.WARNING)


@admin.register(WorkerSchedule)
class WorkerScheduleAdmin(ModelAdmin):
    list_display = ("worker", "weekday", "start_time", "end_time", "is_active")
    list_filter = ("weekday", "is_active")


class WorkerLeaveHistoryInline(TabularInline):
    model = WorkerLeaveHistory
    extra = 0
    can_delete = False
    fields = ("from_status", "to_status", "changed_by", "note", "created_at")
    readonly_fields = fields


@admin.register(WorkerLeave)
class WorkerLeaveAdmin(ModelAdmin):
    list_display = ("worker", "start_at", "end_at", "status", "reviewed_by", "reviewed_at")
    list_filter = ("status", "start_at", "end_at")
    search_fields = ("worker__user__phone", "worker__user__name")
    readonly_fields = ("worker", "start_at", "end_at", "reason", "status", "reviewed_by", "reviewed_at")
    fields = ("worker", "start_at", "end_at", "reason", "status", "admin_note", "reviewed_by", "reviewed_at")
    inlines = (WorkerLeaveHistoryInline,)
    actions = ("approve_leave_requests", "reject_leave_requests")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Approve selected pending leave requests")
    def approve_leave_requests(self, request, queryset):
        from .leave_management import review_worker_leave
        approved = skipped = 0
        for leave_id in queryset.values_list("pk", flat=True):
            try:
                review_worker_leave(leave_id=leave_id, reviewer=request.user, decision=WorkerLeave.Status.APPROVED)
                approved += 1
            except Exception as exc:
                skipped += 1
                self.message_user(request, f"Leave #{leave_id} was not approved: {exc}", messages.WARNING)
        if approved:
            self.message_user(request, f"{approved} leave request(s) approved.", messages.SUCCESS)
        if skipped:
            self.message_user(request, f"{skipped} request(s) need attention; assigned jobs are never changed automatically.", messages.WARNING)

    @admin.action(description="Reject selected pending leave requests (add a note first)")
    def reject_leave_requests(self, request, queryset):
        from .leave_management import review_worker_leave
        rejected = skipped = 0
        for leave in queryset:
            note = leave.admin_note.strip()
            if not note:
                skipped += 1
                continue
            try:
                review_worker_leave(
                    leave_id=leave.pk, reviewer=request.user,
                    decision=WorkerLeave.Status.REJECTED, note=note,
                )
                rejected += 1
            except Exception as exc:
                skipped += 1
                self.message_user(request, f"Leave #{leave.pk} was not rejected: {exc}", messages.WARNING)
        if rejected:
            self.message_user(request, f"{rejected} leave request(s) rejected.", messages.SUCCESS)
        if skipped:
            self.message_user(request, f"{skipped} request(s) skipped. Add a rejection note and select only pending requests.", messages.WARNING)



@admin.register(WorkerEarning)
class WorkerEarningAdmin(ModelAdmin):
    list_display = (
        "id", "worker", "booking", "earning_source", "extra_work", "settlement_batch", "available_at", "gross_amount", "commission_rate",
        "commission_amount", "adjustment_amount", "net_amount", "status", "payout_reference", "paid_at", "paid_by",
    )
    list_filter = ("status", "created_at")
    search_fields = ("worker__user__name", "worker__user__phone", "booking__id", "extra_work__id", "payout_reference")
    readonly_fields = (
        "worker", "booking", "extra_work", "settlement_batch", "available_at", "payment", "gross_amount", "commission_rate",
        "commission_amount", "net_amount", "hold_reason", "paid_at", "paid_by",
        "adjusted_by", "adjusted_at", "created_at", "updated_at",
    )

    @admin.display(description="Earning source")
    def earning_source(self, obj):
        return "AIRway-funded recovery" if getattr(obj.booking, "rework_source", None) is not None else "Customer payment"

    @admin.action(description="Create / update weekly payout batches for selected available earnings")
    def create_weekly_settlements(self, request, queryset):
        from .earnings import create_weekly_worker_settlements
        earning_ids = list(queryset.filter(
            status=WorkerEarning.Status.AVAILABLE,
            settlement_batch__isnull=True,
            net_amount__gt=0,
        ).values_list("pk", flat=True))
        batches = create_weekly_worker_settlements(earning_ids, created_by=request.user)
        if not batches:
            self.message_user(
                request,
                "No unassigned available earnings with a valid payout were selected.",
                level=messages.WARNING,
            )
            return
        self.message_user(
            request,
            f"Created or updated {len(batches)} weekly worker settlement batch(es).",
            level=messages.SUCCESS,
        )

    actions = ("create_weekly_settlements",)

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return bool(
            request.user.is_superuser
            or request.user.has_perm("workers.manage_worker_payouts")
            or request.user.has_perm("workers.configure_worker_commission")
        )

    def has_change_permission(self, request, obj=None):
        return bool(
            request.user.is_superuser
            or request.user.has_perm("workers.manage_worker_payouts")
        )

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj is None:
            fields.extend(["status", "payout_reference", "adjustment_amount", "adjustment_note"])
        elif obj.settlement_batch_id:
            fields.extend(["status", "payout_reference", "adjustment_amount", "adjustment_note"])
        elif obj.status == WorkerEarning.Status.AVAILABLE:
            fields.extend(["status", "payout_reference", "adjustment_amount", "adjustment_note"])
        elif obj.status == WorkerEarning.Status.ON_HOLD:
            fields.append("payout_reference")
        else:
            fields.extend(["status", "payout_reference", "adjustment_amount", "adjustment_note"])
        return tuple(dict.fromkeys(fields))

    def save_model(self, request, obj, form, change):
        if not change:
            raise ValidationError("Worker earning records are created by verified settlement only.")
        previous = WorkerEarning.objects.get(pk=obj.pk)
        if previous.settlement_batch_id and obj.status != previous.status:
            raise ValidationError("This earning is controlled by its weekly settlement batch.")
        if previous.status == WorkerEarning.Status.PAID:
            raise ValidationError("A recorded payout is immutable.")

        if previous.status == WorkerEarning.Status.AVAILABLE and obj.status == WorkerEarning.Status.PAID:
            raise ValidationError("Create and pay a weekly settlement batch instead of paying a job earning individually.")
        elif previous.status == WorkerEarning.Status.ON_HOLD and obj.status == WorkerEarning.Status.AVAILABLE:
            if previous.commission_amount is None:
                raise ValidationError("Configure the worker commission rate before releasing this earning.")
            if not str(obj.adjustment_note or "").strip():
                raise ValidationError("A reconciliation note is required to release an earning hold.")
            from .earnings import calculate_worker_earning_net
            adjusted_net = calculate_worker_earning_net(obj)
            if adjusted_net is None or adjusted_net < 0:
                raise ValidationError("The earning cannot be released until its payout calculation is valid and non-negative.")
            obj.net_amount = adjusted_net
            obj.adjustment_note = obj.adjustment_note.strip()
            obj.adjusted_by = request.user
            obj.adjusted_at = timezone.now()
            obj.hold_reason = previous.hold_reason
        else:
            raise ValidationError("Only available earnings can be paid, or held earnings can be reconciled and released.")
        super().save_model(request, obj, form, change)


class WorkerPayoutSettlementEarningInline(TabularInline):
    model = WorkerEarning
    extra = 0
    can_delete = False
    fields = (
        "booking", "extra_work", "gross_amount", "commission_amount",
        "adjustment_amount", "net_amount", "status", "payout_reference", "paid_at",
    )
    readonly_fields = fields

    def has_view_permission(self, request, obj=None):
        return bool(
            request.user.is_superuser
            or request.user.has_perm("workers.manage_worker_payouts")
        )

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WorkerPayoutSettlement)
class WorkerPayoutSettlementAdmin(ModelAdmin):
    inlines = (WorkerPayoutSettlementEarningInline,)

    list_display = (
        "id", "worker", "period_start", "period_end", "total_amount",
        "status", "payout_reference", "paid_at",
    )
    list_filter = ("status", "period_start", "paid_at")
    search_fields = ("worker__user__name", "worker__user__phone", "payout_reference")
    readonly_fields = (
        "worker", "period_start", "period_end", "total_amount",
        "created_by", "paid_at", "paid_by", "created_at", "updated_at",
    )
    fields = (
        "worker", "period_start", "period_end", "total_amount", "status",
        "payout_reference", "admin_note", "created_by", "paid_at", "paid_by",
        "created_at", "updated_at",
    )

    def save_model(self, request, obj, form, change):
        if not change:
            raise ValidationError("Weekly settlement batches are created from available worker earnings.")
        previous = WorkerPayoutSettlement.objects.get(pk=obj.pk)
        if previous.status == WorkerPayoutSettlement.Status.PAID:
            raise ValidationError("A paid weekly settlement is immutable.")
        if obj.status == WorkerPayoutSettlement.Status.PAID:
            from .earnings import mark_worker_payout_settlement_paid
            mark_worker_payout_settlement_paid(
                obj.pk, obj.payout_reference, request.user
            )
            obj.refresh_from_db()
            return
        if obj.status != previous.status:
            raise ValidationError("Invalid weekly settlement status transition.")
        super().save_model(request, obj, form, change)

    def has_view_permission(self, request, obj=None):
        return bool(
            request.user.is_superuser
            or request.user.has_perm("workers.manage_worker_payouts")
        )

    def has_change_permission(self, request, obj=None):
        return bool(
            request.user.is_superuser
            or request.user.has_perm("workers.manage_worker_payouts")
        )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WorkerRewardWallet)
class WorkerRewardWalletAdmin(ModelAdmin):
    list_display = ("worker", "balance", "total_earned", "total_withdrawn", "eligible_jobs_count", "updated_at")
    search_fields = ("worker__user__name", "worker__user__phone")
    readonly_fields = (
        "worker", "balance", "total_earned", "total_withdrawn",
        "eligible_jobs_count", "created_at", "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WorkerRewardTransaction)
class WorkerRewardTransactionAdmin(ModelAdmin):
    list_display = ("worker", "type", "amount", "milestone_jobs", "booking", "referral", "reference_key", "created_at")
    list_filter = ("type", "created_at")
    search_fields = ("worker__user__phone", "reference_key", "description")
    readonly_fields = (
        "wallet", "worker", "booking", "referral", "type", "amount", "milestone_jobs",
        "reference_key", "description", "created_at", "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WorkerRewardWithdrawal)
class WorkerRewardWithdrawalAdmin(ModelAdmin):
    list_display = ("id", "worker", "amount", "status", "request_key", "payout_upi_id", "payout_reference", "created_at", "processed_at")
    list_filter = ("status", "created_at")
    search_fields = ("worker__user__name", "worker__user__phone", "request_key", "payout_upi_id", "payout_reference")
    readonly_fields = (
        "wallet", "worker", "amount", "request_key", "payout_upi_id", "processed_by",
        "processed_at", "created_at", "updated_at",
    )
    fields = (
        "wallet", "worker", "amount", "request_key", "payout_upi_id", "status",
        "payout_reference", "admin_note", "processed_by", "processed_at",
        "created_at", "updated_at",
    )

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj is not None and obj.status == WorkerRewardWithdrawal.Status.PAID:
            fields.extend(["status", "payout_reference", "admin_note"])
        return tuple(dict.fromkeys(fields))

    def save_model(self, request, obj, form, change):
        if not change:
            super().save_model(request, obj, form, change)
            return

        previous = WorkerRewardWithdrawal.objects.get(pk=obj.pk)
        if previous.status == WorkerRewardWithdrawal.Status.PAID:
            if (
                obj.status != previous.status
                or obj.payout_reference != previous.payout_reference
                or obj.admin_note != previous.admin_note
            ):
                raise ValidationError("A paid reward withdrawal is immutable.")
            return

        previous_status = previous.status
        if previous_status == obj.status:
            super().save_model(request, obj, form, change)
            return

        allowed = {
            WorkerRewardWithdrawal.Status.PENDING: {
                WorkerRewardWithdrawal.Status.APPROVED,
                WorkerRewardWithdrawal.Status.REJECTED,
            },
            WorkerRewardWithdrawal.Status.APPROVED: {
                WorkerRewardWithdrawal.Status.PAID,
                WorkerRewardWithdrawal.Status.REJECTED,
            },
        }
        if obj.status not in allowed.get(previous_status, set()):
            raise ValidationError("Invalid withdrawal status transition.")
        if obj.status == WorkerRewardWithdrawal.Status.PAID and not obj.payout_reference.strip():
            raise ValidationError("A payout reference is required before marking a withdrawal as paid.")

        # Keep wallet ledger updates and the withdrawal status change atomic.
        with transaction.atomic():
            locked = WorkerRewardWithdrawal.objects.select_for_update().get(pk=obj.pk)
            if locked.status != previous_status:
                raise ValidationError("This withdrawal was updated by another admin. Reload and try again.")

            wallet = WorkerRewardWallet.objects.select_for_update().get(pk=locked.wallet_id)
            if obj.status == WorkerRewardWithdrawal.Status.REJECTED:
                refund, created = WorkerRewardTransaction.objects.get_or_create(
                    reference_key=f"mission-withdrawal-refund:{locked.pk}",
                    defaults={
                        "wallet": wallet,
                        "worker": locked.worker,
                        "type": WorkerRewardTransaction.Type.REFUND,
                        "amount": locked.amount,
                        "description": f"Refund for rejected mission withdrawal #{locked.pk}",
                    },
                )
                if created:
                    wallet.balance += locked.amount
                    wallet.save(update_fields=["balance", "updated_at"])
            elif obj.status == WorkerRewardWithdrawal.Status.PAID:
                wallet.total_withdrawn += locked.amount
                wallet.save(update_fields=["total_withdrawn", "updated_at"])

            obj.processed_by = request.user
            obj.processed_at = timezone.now()
            super().save_model(request, obj, form, change)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WorkerReferralSettings)
class WorkerReferralSettingsAdmin(ModelAdmin):
    list_display = ("reward_amount", "is_active", "updated_at")
    fields = ("reward_amount", "is_active", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")

    def has_add_permission(self, request):
        return not WorkerReferralSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WorkerMonthlyMissionProgress)
class WorkerMonthlyMissionProgressAdmin(ModelAdmin):
    list_display = ("worker", "month_start", "eligible_jobs_count", "achieved_milestones", "updated_at")
    list_filter = ("month_start",)
    search_fields = ("worker__user__name", "worker__user__phone")
    readonly_fields = ("worker", "month_start", "eligible_jobs_count", "created_at", "updated_at")

    @admin.display(description="Achieved milestones")
    def achieved_milestones(self, obj):
        reached = [str(value) for value in (5, 15, 25) if obj.eligible_jobs_count >= value]
        return ", ".join(reached) if reached else "None"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
