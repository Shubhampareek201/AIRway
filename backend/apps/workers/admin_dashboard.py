from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import WorkerDocument, WorkerProfile
from .approval import approve_worker, get_approval_requirements
from .models import WorkerService


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
    requirements = get_approval_requirements(worker)

    return render(request, "workers/admin_dashboard/application_detail.html", {
        "worker": worker,
        "documents": documents,
        "has_verified_id": requirements["has_verified_id"],
        "has_photo": requirements["has_verified_photo"],
        "has_verified_photo": requirements["has_verified_photo"],
        "has_service": requirements["has_service"],
        "has_zone": requirements["has_zone"],
        "has_schedule": requirements["has_schedule"],
        "approval_requirements": requirements,
        "can_approve": (
            worker.status == WorkerProfile.Status.PENDING
            and requirements["eligible"]
        ),
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
def verify_service_capabilities(request, worker_id, service_link_id):
    worker = get_object_or_404(WorkerProfile, pk=worker_id)
    link = get_object_or_404(WorkerService, pk=service_link_id, worker=worker)
    if worker.status not in (WorkerProfile.Status.PENDING, WorkerProfile.Status.APPROVED):
        messages.error(request, "Capabilities can only be reviewed for pending or approved workers.")
    elif not link.capabilities:
        messages.error(request, "No task capabilities were submitted for this service.")
    else:
        link.capabilities_verified = True
        link.save(update_fields=["capabilities_verified", "updated_at"])
        messages.success(request, f"Capabilities verified for {link.service.title}.")
    return redirect("admin_dashboard:application_detail", worker_id=worker.pk)


@require_POST
@super_admin_required
def approve_application(request, worker_id):
    result = approve_worker(worker_id, request.user)

    if result["status"] == "approved":
        worker = result["worker"]
        messages.success(
            request,
            f"{worker.user.name or worker.user.phone} has been approved.",
        )
    elif result["status"] == "ineligible":
        messages.error(
            request,
            "This application cannot be approved yet. Missing requirements: "
            + "; ".join(result["requirements"]["missing"]),
        )
    elif result["status"] == "already_processed":
        messages.error(request, "This application is no longer pending.")
    else:
        messages.error(request, "This worker application could not be found.")

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
