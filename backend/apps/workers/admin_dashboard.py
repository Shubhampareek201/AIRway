from django.contrib import messages
from django.contrib.admin.models import LogEntry, CHANGE
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import user_passes_test
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q, Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.bookings.models import Booking, BookingStatusHistory, Order
from apps.catalog.models import Category, Service
from apps.payments.models import Payment, PaymentRefund
from apps.workers.models import WorkerDocument, WorkerProfile
from .approval import approve_worker, get_approval_requirements


def _is_super_admin(user):
    return user.is_authenticated and user.is_active and user.is_staff and user.is_superuser


super_admin_required = user_passes_test(_is_super_admin, login_url="admin_dashboard:login")


def _audit(request, obj, message):
    """Write custom-dashboard mutations to Django's standard admin activity log."""
    LogEntry.objects.create(
        user_id=request.user.pk,
        content_type=ContentType.objects.get_for_model(obj),
        object_id=str(obj.pk),
        object_repr=str(obj)[:200],
        action_flag=CHANGE,
        change_message=message,
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
        "customers": User.objects.filter(Q(active_mode=User.Mode.CUSTOMER) | Q(roles__role="customer")).distinct().count(),
        "professionals": WorkerProfile.objects.count(),
        "pending": WorkerProfile.objects.filter(status=WorkerProfile.Status.PENDING).count(),
        "approved": WorkerProfile.objects.filter(status=WorkerProfile.Status.APPROVED).count(),
        "suspended": WorkerProfile.objects.filter(status=WorkerProfile.Status.SUSPENDED).count(),
        "bookings": Booking.objects.count(),
        "attention": Booking.objects.filter(status__in=[Booking.Status.PENDING, Booking.Status.DISPUTED]).count(),
        "orders": Order.objects.count(),
        "payments_pending": Payment.objects.filter(status=Payment.Status.PENDING).count(),
        "refunds_attention": PaymentRefund.objects.filter(status__in=[
            PaymentRefund.Status.PROCESSING, PaymentRefund.Status.PENDING, PaymentRefund.Status.FAILED
        ]).count(),
    }
    recent_applications = WorkerProfile.objects.select_related("user").prefetch_related(
        "worker_services__service"
    ).order_by("-created_at")[:6]
    recent_bookings = Booking.objects.select_related(
        "customer", "service", "assignment__worker__user"
    ).order_by("-created_at")[:8]
    return render(request, "workers/admin_dashboard/dashboard.html", {
        "counts": counts,
        "recent_applications": recent_applications,
        "recent_bookings": recent_bookings,
        "active_page": "dashboard",
    })


@super_admin_required
def applications(request):
    status_filter = request.GET.get("status", "pending")
    allowed = {value for value, _label in WorkerProfile.Status.choices}
    if status_filter not in allowed and status_filter != "all":
        status_filter = "pending"
    query = request.GET.get("q", "").strip()
    queryset = WorkerProfile.objects.select_related("user").prefetch_related(
        "documents", "worker_services__service", "worker_zones__zone"
    )
    if status_filter != "all":
        queryset = queryset.filter(status=status_filter)
    if query:
        queryset = queryset.filter(
            Q(user__name__icontains=query) | Q(user__phone__icontains=query)
            | Q(user__email__icontains=query)
        )
    return render(request, "workers/admin_dashboard/applications.html", {
        "workers": queryset.order_by("-created_at"),
        "status_filter": status_filter,
        "query": query,
        "active_page": "applications",
    })


@super_admin_required
def professionals(request):
    status_filter = request.GET.get("status", "approved")
    allowed = {value for value, _label in WorkerProfile.Status.choices}
    if status_filter not in allowed and status_filter != "all":
        status_filter = "approved"
    query = request.GET.get("q", "").strip()
    queryset = WorkerProfile.objects.select_related("user").prefetch_related(
        "worker_services__service", "worker_zones__zone"
    )
    if status_filter != "all":
        queryset = queryset.filter(status=status_filter)
    if query:
        queryset = queryset.filter(
            Q(user__name__icontains=query) | Q(user__phone__icontains=query)
            | Q(user__email__icontains=query)
        )
    return render(request, "workers/admin_dashboard/professionals.html", {
        "workers": queryset.order_by("-updated_at"),
        "status_filter": status_filter,
        "query": query,
        "active_page": "professionals",
    })


@super_admin_required
def customers(request):
    query = request.GET.get("q", "").strip()
    queryset = User.objects.filter(Q(active_mode=User.Mode.CUSTOMER) | Q(roles__role="customer")).prefetch_related(
        "addresses", "bookings"
    )
    if query:
        queryset = queryset.filter(
            Q(name__icontains=query) | Q(phone__icontains=query) | Q(email__icontains=query)
        )
    return render(request, "workers/admin_dashboard/customers.html", {
        "customers": queryset.distinct().order_by("-created_at")[:200],
        "query": query,
        "active_page": "customers",
    })


@super_admin_required
def bookings(request):
    status_filter = request.GET.get("status", "all")
    allowed = {value for value, _label in Booking.Status.choices}
    if status_filter not in allowed and status_filter != "all":
        status_filter = "all"
    query = request.GET.get("q", "").strip()
    queryset = Booking.objects.select_related(
        "customer", "service", "variant", "assignment__worker__user", "order_item__order"
    ).prefetch_related("status_history")
    if status_filter != "all":
        queryset = queryset.filter(status=status_filter)
    if query:
        queryset = queryset.filter(
            Q(customer__name__icontains=query) | Q(customer__phone__icontains=query)
            | Q(service__title__icontains=query)
        )
        if query.isdigit():
            queryset = queryset | Booking.objects.filter(pk=int(query)).select_related(
                "customer", "service", "variant", "assignment__worker__user", "order_item__order"
            )
    return render(request, "workers/admin_dashboard/bookings.html", {
        "bookings": queryset.order_by("-created_at")[:200],
        "status_filter": status_filter,
        "query": query,
        "active_page": "bookings",
    })


@super_admin_required
def payments(request):
    status_filter = request.GET.get("status", "all")
    allowed = {value for value, _label in Payment.Status.choices}
    if status_filter not in allowed and status_filter != "all":
        status_filter = "all"
    query = request.GET.get("q", "").strip()
    queryset = Payment.objects.select_related("customer", "order", "booking")
    if status_filter != "all":
        queryset = queryset.filter(status=status_filter)
    if query:
        queryset = queryset.filter(
            Q(customer__name__icontains=query) | Q(customer__phone__icontains=query)
            | Q(razorpay_order_id__icontains=query) | Q(razorpay_payment_id__icontains=query)
            | Q(order__id__icontains=query) | Q(booking__id__icontains=query)
        )
    refunds = PaymentRefund.objects.select_related(
        "payment", "booking", "booking__customer"
    ).order_by("-created_at")[:20]
    return render(request, "workers/admin_dashboard/payments.html", {
        "payments": queryset.order_by("-created_at")[:200],
        "refunds": refunds,
        "status_filter": status_filter,
        "query": query,
        "active_page": "payments",
    })


@super_admin_required
def catalogue(request):
    active = Service.objects.filter(is_active=True)
    services_without_image = active.filter(Q(image="") | Q(image__isnull=True)).count()
    services_without_variants = active.annotate(
        active_variants=Count("variants", filter=Q(variants__is_active=True))
    ).filter(active_variants=0).count()
    services_without_workers = active.annotate(
        approved_workers=Count(
            "assigned_workers",
            filter=Q(assigned_workers__worker__status=WorkerProfile.Status.APPROVED),
        )
    ).filter(approved_workers=0).count()
    return render(request, "workers/admin_dashboard/catalogue.html", {
        "category_count": Category.objects.count(),
        "active_category_count": Category.objects.filter(is_active=True).count(),
        "service_count": Service.objects.count(),
        "active_service_count": active.count(),
        "services_without_image": services_without_image,
        "services_without_variants": services_without_variants,
        "services_without_workers": services_without_workers,
        "active_page": "catalogue",
    })


@super_admin_required
def activity(request):
    admin_entries = list(LogEntry.objects.select_related("user", "content_type").order_by("-action_time")[:30])
    booking_entries = list(BookingStatusHistory.objects.select_related(
        "booking", "changed_by", "booking__customer"
    ).order_by("-created_at")[:30])
    events = []
    for entry in admin_entries:
        events.append({
            "when": entry.action_time,
            "actor": entry.user.name or entry.user.phone,
            "subject": entry.object_repr,
            "detail": entry.get_change_message() or "Admin record updated",
            "kind": "Admin change",
        })
    for entry in booking_entries:
        events.append({
            "when": entry.created_at,
            "actor": (entry.changed_by.name or entry.changed_by.phone) if entry.changed_by else "System",
            "subject": f"Booking #{entry.booking_id}",
            "detail": f"{entry.from_status or 'Created'} → {entry.to_status}. {entry.note}".strip(),
            "kind": "Booking update",
        })
    events.sort(key=lambda event: event["when"], reverse=True)
    return render(request, "workers/admin_dashboard/activity.html", {
        "events": events[:50],
        "active_page": "activity",
    })


@require_POST
@super_admin_required
def update_professional_status(request, worker_id):
    worker = get_object_or_404(WorkerProfile.objects.select_related("user"), pk=worker_id)
    action = request.POST.get("action", "").strip()
    reason = request.POST.get("reason", "").strip()
    if not reason:
        messages.error(request, "Please add a reason so this status change is recorded.")
    elif action == "suspend" and worker.status == WorkerProfile.Status.APPROVED:
        worker.status = WorkerProfile.Status.SUSPENDED
        worker.is_online = False
        worker.save(update_fields=["status", "is_online", "updated_at"])
        _audit(request, worker, f"Professional suspended: {reason}")
        messages.success(request, "Professional suspended and set offline.")
    elif action == "restore" and worker.status == WorkerProfile.Status.SUSPENDED:
        worker.status = WorkerProfile.Status.APPROVED
        worker.is_online = False
        worker.save(update_fields=["status", "is_online", "updated_at"])
        _audit(request, worker, f"Professional restored to approved status (remains offline): {reason}")
        messages.success(request, "Professional restored to approved status and remains offline.")
    else:
        messages.error(request, "This status transition is not allowed.")
    return redirect("admin_dashboard:application_detail", worker_id=worker_id)


@super_admin_required
def application_detail(request, worker_id):
    worker = get_object_or_404(
        WorkerProfile.objects.select_related("user", "approved_by").prefetch_related(
            "documents__verified_by", "worker_services__service",
            "worker_zones__zone", "schedules",
        ), pk=worker_id,
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
        "can_approve": worker.status == WorkerProfile.Status.PENDING and requirements["eligible"],
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
        _audit(request, document, "Document verified")
        messages.success(request, "Document marked as verified.")
    elif decision == "reject":
        document.status = WorkerDocument.Status.REJECTED
        document.verified_by = None
        document.save(update_fields=["status", "verified_by", "updated_at"])
        _audit(request, document, "Document rejected")
        messages.success(request, "Document marked as rejected.")
    else:
        messages.error(request, "Invalid document action.")
    return redirect("admin_dashboard:application_detail", worker_id=worker.pk)


@require_POST
@super_admin_required
def approve_application(request, worker_id):
    result = approve_worker(worker_id, request.user)
    if result["status"] == "approved":
        worker = result["worker"]
        _audit(request, worker, "Worker application approved; worker remains offline")
        messages.success(request, f"{worker.user.name or worker.user.phone} has been approved and remains offline.")
    elif result["status"] == "ineligible":
        messages.error(request, "This application cannot be approved yet. Missing requirements: " + "; ".join(result["requirements"]["missing"]))
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
        _audit(request, worker, f"Worker application rejected: {reason}")
        messages.success(request, "Worker application rejected.")
    return redirect("admin_dashboard:application_detail", worker_id=worker_id)
