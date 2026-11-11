from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import user_passes_test
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import UserRole
from .models import WorkerDocument, WorkerProfile


def _is_super_admin(user):
    return user.is_authenticated and user.is_active and user.is_staff and user.is_superuser


super_admin_required = user_passes_test(
    _is_super_admin,
    login_url="admin_dashboard:login",
)


def admin_login(request):
    if _is_super_admin(request.user):
        return redirect("admin_dashboard:dashboard")

    error = ""
    if request.method == "POST":
        phone = request.POST.get("phone", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, phone=phone, password=password)
        if user is not None and _is_super_admin(user):
            login(request, user)
            return redirect("admin_dashboard:dashboard")
        error = "Phone number or password is incorrect, or this account is not the Super Admin."

    return render(request, "workers/admin_dashboard/login.html", {"error": error})


@require_POST
@super_admin_required
def admin_logout(request):
    logout(request)
    return redirect("admin_dashboard:login")


@super_admin_required
def dashboard(request):
    counts = {
        "pending": WorkerProfile.objects.filter(status=WorkerProfile.Status.PENDING).count(),
        "approved": WorkerProfile.objects.filter(status=WorkerProfile.Status.APPROVED).count(),
        "rejected": WorkerProfile.objects.filter(status=WorkerProfile.Status.REJECTED).count(),
        "suspended": WorkerProfile.objects.filter(status=WorkerProfile.Status.SUSPENDED).count(),
        "total": WorkerProfile.objects.count(),
    }
    recent = (
        WorkerProfile.objects.select_related("user")
        .order_by("-created_at")[:6]
    )
    return render(request, "workers/admin_dashboard/dashboard.html", {
        "counts": counts,
        "recent_applications": recent,
        "active_page": "dashboard",
    })


@super_admin_required
def applications(request):
    status_filter = request.GET.get("status", "pending")
    allowed_statuses = {value for value, _label in WorkerProfile.Status.choices}
    if status_filter not in allowed_statuses and status_filter != "all":
        status_filter = "pending"

    query = request.GET.get("q", "").strip()
    queryset = WorkerProfile.objects.select_related("user").prefetch_related(
        "documents", "worker_services__service", "worker_zones__zone"
    )
    if status_filter != "all":
        queryset = queryset.filter(status=status_filter)
    if query:
        queryset = queryset.filter(
            Q(user__name__icontains=query)
            | Q(user__phone__icontains=query)
            | Q(user__email__icontains=query)
        )

    return render(request, "workers/admin_dashboard/applications.html", {
        "workers": queryset.order_by("-created_at"),
        "status_filter": status_filter,
        "query": query,
        "active_page": "applications",
    })


@super_admin_required
def application_detail(request, worker_id):
    worker = get_object_or_404(
        WorkerProfile.objects.select_related("user", "approved_by").prefetch_related(
            "documents__verified_by",
            "worker_services__service",
            "worker_zones__zone",
            "schedules",
        ),
        pk=worker_id,
    )
    documents = list(worker.documents.all())
    has_verified_id = any(
        doc.doc_type in (WorkerDocument.DocumentType.AADHAAR, WorkerDocument.DocumentType.ID)
        and doc.status == WorkerDocument.Status.VERIFIED
        for doc in documents
    )
    has_photo = any(
        doc.doc_type == WorkerDocument.DocumentType.PHOTO
        and doc.status == WorkerDocument.Status.VERIFIED
        for doc in documents
    )
    has_service = worker.worker_services.filter(
        service__is_active=True, service__category__is_active=True
    ).exists()
    has_zone = worker.worker_zones.filter(
        zone__is_active=True, zone__city__is_active=True
    ).exists()
    has_schedule = worker.schedules.filter(is_active=True).exists()
    can_approve = (
        worker.status == WorkerProfile.Status.PENDING
        and has_verified_id and has_photo and has_service and has_zone and has_schedule
    )
    return render(request, "workers/admin_dashboard/application_detail.html", {
        "worker": worker,
        "documents": documents,
        "has_verified_id": has_verified_id,
        "has_photo": has_photo,
        "has_service": has_service,
        "has_zone": has_zone,
        "has_schedule": has_schedule,
        "can_approve": can_approve,
        "active_page": "applications",
    })


@require_POST
@super_admin_required
def review_document(request, worker_id, document_id):
    worker = get_object_or_404(WorkerProfile, pk=worker_id)
    document = get_object_or_404(WorkerDocument, pk=document_id, worker=worker)
    decision = request.POST.get("decision")
    if worker.status != WorkerProfile.Status.PENDING:
        messages.error(request, "Only pending applications can have documents reviewed.")
    elif decision == "verify":
        document.status = WorkerDocument.Status.VERIFIED
        document.verified_by = request.user
        document.save(update_fields=["status", "verified_by", "updated_at"])
        messages.success(request, "Document marked as verified.")
    elif decision == "reject":
        document.status = WorkerDocument.Status.REJECTED
        document.verified_by = None
        document.save(update_fields=["status", "verified_by", "updated_at"])
        messages.success(request, "Document marked as rejected.")
    else:
        messages.error(request, "Invalid document action.")
    return redirect("admin_dashboard:application_detail", worker_id=worker.pk)


@require_POST
@super_admin_required
def approve_application(request, worker_id):
    with transaction.atomic():
        worker = get_object_or_404(
            WorkerProfile.objects.select_for_update().select_related("user"),
            pk=worker_id,
        )
        has_verified_id = worker.documents.filter(
            doc_type__in=[WorkerDocument.DocumentType.AADHAAR, WorkerDocument.DocumentType.ID],
            status=WorkerDocument.Status.VERIFIED,
        ).exists()
        if worker.status != WorkerProfile.Status.PENDING:
            messages.error(request, "This application is no longer pending.")
        elif (
            not has_verified_id
            or not worker.documents.filter(
                doc_type=WorkerDocument.DocumentType.PHOTO,
                status=WorkerDocument.Status.VERIFIED,
            ).exists()
            or not worker.worker_services.filter(
                service__is_active=True, service__category__is_active=True
            ).exists()
            or not worker.worker_zones.filter(
                zone__is_active=True, zone__city__is_active=True
            ).exists()
            or not worker.schedules.filter(is_active=True).exists()
        ):
            messages.error(request, "Approval requires a verified ID and photo, active services, an active service area, and working hours.")
        else:
            from django.utils import timezone
            worker.status = WorkerProfile.Status.APPROVED
            worker.approved_by = request.user
            worker.approved_at = timezone.now()
            worker.rejection_reason = ""
            worker.save()
            UserRole.objects.get_or_create(user=worker.user, role=UserRole.Role.WORKER)
            messages.success(request, f"{worker.user.name or worker.user.phone} has been approved.")
    return redirect("admin_dashboard:application_detail", worker_id=worker_id)


@require_POST
@super_admin_required
def reject_application(request, worker_id):
    reason = request.POST.get("reason", "").strip()
    worker = get_object_or_404(WorkerProfile, pk=worker_id)
    if worker.status != WorkerProfile.Status.PENDING:
        messages.error(request, "Only pending applications can be rejected.")
    elif not reason:
        messages.error(request, "Please enter a rejection reason.")
    else:
        worker.status = WorkerProfile.Status.REJECTED
        worker.rejection_reason = reason
        worker.is_online = False
        worker.save(update_fields=["status", "rejection_reason", "is_online", "updated_at"])
        messages.success(request, "Worker application rejected.")
    return redirect("admin_dashboard:application_detail", worker_id=worker_id)
