from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
from django.shortcuts import get_object_or_404
from django.core.exceptions import ObjectDoesNotExist

from .models import Booking, BookingStatusHistory, CustomerCart, CartItem, Order, OrderItem, BookingAddOn, WorkerOffer
from .serializers import (
    BookingCreateSerializer,
    BookingListSerializer,
    BookingDetailSerializer,
    BookingCancelSerializer,
    BookingAvailabilitySerializer,
    CartItemSerializer,
    CustomerCartSerializer,
)
from .services import check_slot_availability, check_service_available, create_worker_offers_for_booking, SlotConflictError, ServiceUnavailableError
from apps.notifications.models import Notification
from apps.accounts.models import Address
from apps.catalog.audience import validate_beauty_audience


class BookingViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = Booking.objects.filter(customer=user).select_related(
            "service", "variant", "address", "assignment__worker__user"
        ).prefetch_related(
            "booking_addons__addon", "form_responses__form_field", "status_history"
        )

        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)

        return queryset

    def get_serializer_class(self):
        if self.action == "create":
            return BookingCreateSerializer
        elif self.action == "list":
            return BookingListSerializer
        return BookingDetailSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()

        detail_serializer = BookingDetailSerializer(booking, context={"request": request})
        return Response(detail_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        from apps.bookings.models import WorkerOffer

        booking = self.get_object()
        serializer = BookingCancelSerializer(data=request.data, context={"booking": booking})
        serializer.is_valid(raise_exception=True)

        reason = serializer.validated_data.get("reason", "")
        old_status = booking.status

        booking.status = Booking.Status.CANCELLED
        booking.cancelled_at = timezone.now()
        booking.cancellation_reason = reason
        booking.cancelled_by = request.user
        booking.save()

        BookingStatusHistory.objects.create(
            booking=booking,
            from_status=old_status,
            to_status=Booking.Status.CANCELLED,
            changed_by=request.user,
            note=f"Cancelled by customer. Reason: {reason}",
        )

        # Cancel all pending worker offers for this booking
        WorkerOffer.objects.filter(booking=booking, status=WorkerOffer.Status.PENDING).update(
            status=WorkerOffer.Status.EXPIRED,
            responded_at=timezone.now(),
        )

        Notification.objects.create(
            user=request.user,
            type=Notification.Type.BOOKING_CANCELLED,
            title="Booking Cancelled",
            body="Your booking has been cancelled.",
            channel=Notification.Channel.IN_APP,
            data={"booking_id": booking.id},
        )

        return Response({"detail": "Booking cancelled successfully.", "status": booking.status})

    @action(detail=True, methods=["post"], url_path="confirm")
    def confirm_booking(self, request, pk=None):
        """Confirm a booking and trigger worker offer creation."""
        from apps.notifications.models import Notification

        booking = self.get_object()

        if booking.customer != request.user:
            return Response(
                {"detail": "Only the booking owner can confirm this booking."},
                status=status.HTTP_403_FORBIDDEN
            )

        if booking.status != Booking.Status.PENDING:
            return Response(
                {"detail": f"Booking cannot be confirmed in {booking.get_status_display()} state."},
                status=status.HTTP_400_BAD_REQUEST
            )

        old_status = booking.status
        booking.status = Booking.Status.CONFIRMED
        booking.save()

        BookingStatusHistory.objects.create(
            booking=booking,
            from_status=old_status,
            to_status=Booking.Status.CONFIRMED,
            changed_by=request.user,
            note="Customer confirmed booking",
        )

        # Create worker offers for this booking
        offers = create_worker_offers_for_booking(booking)

        # Notify customer about confirm
        Notification.objects.create(
            user=booking.customer,
            type=Notification.Type.BOOKING_CONFIRMED,
            title="Booking Confirmed",
            body="Your booking is confirmed. A worker will be assigned soon.",
            channel=Notification.Channel.IN_APP,
            data={"booking_id": booking.id},
        )

        return Response({
            "detail": "Booking confirmed and worker offers created.",
            "status": booking.status,
            "offers_count": len(offers),
        })

    @action(detail=False, methods=["post"])
    def check_availability(self, request, pk=None):
        """Check if a slot is available for booking."""
        serializer = BookingAvailabilitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        service = data["service_obj"]
        variant = data["variant"]
        booking_mode = data["booking_mode"]
        scheduled_at = data["scheduled_at"]
        drop_scheduled_at = data.get("drop_scheduled_at")
        category_answers = data.get("category_answers", {})

        from apps.workers.eligibility import required_worker_gender_for_booking
        try:
            validate_beauty_audience(service, category_answers)
            required_gender = required_worker_gender_for_booking(service, category_answers)
        except ValueError as exc:
            return Response({"available": False, "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        address = None
        if data.get("address_id"):
            address = Address.objects.filter(
                pk=data["address_id"],
                user=request.user,
                deleted_at__isnull=True,
            ).select_related("zone__city").first()
            if address is None:
                return Response({"detail": "Select a valid service address."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            check_service_available(
                service=service,
                address=address,
                audience=data.get("audience", "all"),
            )

            duration = variant.duration_minutes if variant else service.duration_minutes
            duration = (duration or 60) * data.get("quantity", 1)

            check_slot_availability(
                service=service,
                scheduled_at=scheduled_at,
                duration_minutes=duration,
                booking_mode=booking_mode,
                drop_scheduled_at=drop_scheduled_at,
            )
            if required_gender:
                from apps.bookings.services import has_eligible_worker_for_slot
                if not has_eligible_worker_for_slot(
                    service=service,
                    address=address,
                    scheduled_at=scheduled_at,
                    duration_minutes=duration,
                    required_gender=required_gender,
                    drop_scheduled_at=drop_scheduled_at if booking_mode == Booking.BookingMode.PICKUP_DROP else None,
                    exclude_customer_id=request.user.id,
                ):
                    preference_can_change = (
                        category_answers.get("professional_preference") == "female"
                        and not service.requires_female_worker
                    )
                    return Response({
                        "available": False,
                        "message": (
                            "No female professional is available for this time slot. "
                            "Choose another time or change the preference to No preference."
                            if preference_can_change
                            else "No female professional is available for this service at the selected time. Choose another time."
                        ),
                        "reason": (
                            "female_professional_unavailable"
                            if preference_can_change
                            else "required_female_worker_unavailable"
                        ),
                    })

            return Response({"available": True, "message": "Slot is available for booking."})

        except SlotConflictError as e:
            return Response(
                {"available": False, "message": str(e)},
                status=status.HTTP_409_CONFLICT,
            )
        except ServiceUnavailableError as e:
            return Response(
                {"available": False, "message": str(e)},
                status=status.HTTP_200_OK,
            )

    @action(detail=True, methods=["get", "post"])
    def track(self, request, pk=None):
        booking = self.get_object()

        if not hasattr(booking, "assignment") or not booking.assignment:
            return Response(
                {"detail": "No worker assigned to this booking yet.", "is_assigned": False},
                status=status.HTTP_200_OK,
            )

        assignment = booking.assignment
        worker = assignment.worker

        # Check if worker is online and return tracking info
        return Response({
            "is_assigned": True,
            "worker_id": worker.id,
            "worker_name": worker.user.name or worker.user.phone,
            "worker_phone": worker.user.phone,
            "worker_rating": float(worker.rating_avg) if worker.rating_avg else None,
            "status": booking.status,
            "assigned_at": assignment.assigned_at,
            "started_at": assignment.started_at,
            # Live worker GPS is not stored by the current WorkerProfile model.
            # Never fabricate a position from the customer's address; clients should
            # show "location unavailable" until a verified worker GPS source is added.
            "worker_latitude": None,
            "worker_longitude": None,
        })
    @action(detail=True, methods=["post"], url_path="start")
    def start_job(self, request, pk=None):
        """Mark booking as in progress (worker started the job)."""
        from apps.notifications.models import Notification

        booking = Booking.objects.filter(pk=pk).first()
        if not booking:
            return Response({"detail": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

        assignment = getattr(booking, "assignment", None)

        if not assignment:
            return Response(
                {"detail": "This booking has no assignment. Worker must accept offer first."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user_worker_profile = request.user.worker_profile
        except ObjectDoesNotExist:
            return Response(
                {"detail": "User is not a worker."},
                status=status.HTTP_403_FORBIDDEN
            )

        if assignment.worker != user_worker_profile:
            return Response(
                {"detail": "Only the assigned worker can start this job."},
                status=status.HTTP_403_FORBIDDEN
            )

        if booking.status not in (Booking.Status.ASSIGNED, Booking.Status.CONFIRMED):
            return Response(
                {"detail": f"Cannot start job in {booking.get_status_display()} state."},
                status=status.HTTP_400_BAD_REQUEST
            )

        old_status = booking.status
        booking.status = Booking.Status.IN_PROGRESS
        booking.save()

        BookingStatusHistory.objects.create(
            booking=booking,
            from_status=old_status,
            to_status=Booking.Status.IN_PROGRESS,
            changed_by=request.user,
            note="Worker started the job",
        )

        if assignment:
            assignment.started_at = timezone.now()
            assignment.save()

        Notification.objects.create(
            user=booking.customer,
            type=Notification.Type.BOOKING_STARTED,
            title="Service Started",
            body="The service has started. You'll receive updates.",
            channel=Notification.Channel.IN_APP,
            data={"booking_id": booking.id},
        )

        return Response({
            "detail": "Job marked as started.",
            "status": booking.status,
            "started_at": assignment.started_at,
        })

    @action(detail=True, methods=["post"], url_path="complete")
    def complete_job(self, request, pk=None):
        """Mark booking as completed (worker finished the job)."""
        from apps.notifications.models import Notification

        booking = Booking.objects.filter(pk=pk).first()
        if not booking:
            return Response({"detail": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

        assignment = getattr(booking, "assignment", None)

        if not assignment:
            return Response(
                {"detail": "This booking has no assignment."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user_worker_profile = request.user.worker_profile
        except ObjectDoesNotExist:
            return Response(
                {"detail": "User is not a worker."},
                status=status.HTTP_403_FORBIDDEN
            )

        if assignment.worker != user_worker_profile:
            return Response(
                {"detail": "Only the assigned worker can complete this job."},
                status=status.HTTP_403_FORBIDDEN
            )

        if booking.status != Booking.Status.IN_PROGRESS:
            return Response(
                {"detail": f"Cannot complete job in {booking.get_status_display()} state."},
                status=status.HTTP_400_BAD_REQUEST
            )

        old_status = booking.status
        booking.status = Booking.Status.COMPLETED
        booking.completed_at = timezone.now()
        booking.save()

        BookingStatusHistory.objects.create(
            booking=booking,
            from_status=old_status,
            to_status=Booking.Status.COMPLETED,
            changed_by=request.user,
            note="Worker completed the job",
        )

        if assignment:
            assignment.completed_at = timezone.now()
            assignment.save()

        Notification.objects.create(
            user=booking.customer,
            type=Notification.Type.BOOKING_COMPLETED,
            title="Service Completed",
            body="The service has been completed successfully.",
            channel=Notification.Channel.IN_APP,
            data={"booking_id": booking.id},
        )

        return Response({
            "detail": "Job marked as completed.",
            "status": booking.status,
            "completed_at": assignment.completed_at,
        })


class CustomerCheckoutView(APIView):
    """Convert a customer's cart into one parent order with independent bookings."""

    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        cart = get_object_or_404(
            CustomerCart.objects.select_for_update().prefetch_related(
                "items__service", "items__variant"
            ),
            customer=request.user,
        )
        items = list(cart.items.all())
        if not items:
            return Response({"detail": "Your cart is empty."}, status=status.HTTP_400_BAD_REQUEST)
        if not cart.address_id:
            return Response({"detail": "Select a service address before checkout."}, status=status.HTTP_400_BAD_REQUEST)

        requested = request.data.get("items")
        if not isinstance(requested, list) or not requested:
            return Response(
                {"detail": "items must contain cart_item_id, scheduled_at and optional drop_scheduled_at for every cart item."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        requested_by_id = {}
        for row in requested:
            if not isinstance(row, dict) or not row.get("cart_item_id"):
                return Response({"detail": "Each checkout item needs a cart_item_id."}, status=status.HTTP_400_BAD_REQUEST)
            try:
                item_id = int(row["cart_item_id"])
            except (TypeError, ValueError):
                return Response({"detail": "cart_item_id must be an integer."}, status=status.HTTP_400_BAD_REQUEST)
            if item_id in requested_by_id:
                return Response({"detail": "Duplicate cart_item_id values are not allowed."}, status=status.HTTP_400_BAD_REQUEST)
            requested_by_id[item_id] = row

        if set(requested_by_id) != {item.id for item in items}:
            return Response(
                {"detail": "Checkout must include every current cart item exactly once."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        prepared = []
        for item in items:
            try:
                check_service_available(service=item.service, address=cart.address, audience="all")
            except ServiceUnavailableError as exc:
                return Response(
                    {"detail": str(exc), "cart_item_id": item.id},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            schedule = requested_by_id[item.id]
            booking_data = {
                "service": item.service_id,
                "variant": item.variant_id,
                "booking_mode": item.service.booking_mode,
                "scheduled_at": schedule.get("scheduled_at"),
                "drop_scheduled_at": schedule.get("drop_scheduled_at"),
                "address_id": cart.address_id,
                "addon_ids": [row["id"] for row in item.addon_selections],
                "form_responses": item.form_answers,
                "category_answers": item.category_answers,
                "quantity": item.quantity,
                "notes": item.notes,
            }
            serializer = BookingCreateSerializer(
                data=booking_data,
                context={"request": request, "defer_worker_dispatch": True},
            )
            serializer.is_valid(raise_exception=True)
            prepared.append((item, serializer))

        order = Order.objects.create(
            customer=request.user,
            address=cart.address,
            status=Order.Status.AWAITING_ASSIGNMENT,
        )
        subtotal = Decimal("0")
        tax_total = Decimal("0")
        grand_total = Decimal("0")
        dispatch_results = []

        for item, serializer in prepared:
            booking = serializer.save()
            quantity = item.quantity
            base_snapshot = dict(booking.pricing_snapshot or {})
            unit_subtotal = Decimal(str(base_snapshot.get("subtotal", "0")))

            # Preserve add-on quantities chosen in the cart and make the
            # immutable booking/order price snapshots reflect those quantities.
            addon_quantities = {row["id"]: int(row.get("quantity", 1)) for row in item.addon_selections}
            adjusted_addons = []
            adjusted_addons_total = Decimal("0")
            for booking_addon in booking.booking_addons.select_related("addon"):
                addon_quantity = addon_quantities.get(booking_addon.addon_id, 1)
                booking_addon.quantity = addon_quantity
                booking_addon.total_price = booking_addon.unit_price * addon_quantity
                booking_addon.save(update_fields=["quantity", "total_price", "updated_at"])
                adjusted_addons_total += booking_addon.total_price
                adjusted_addons.append({
                    "id": booking_addon.addon_id,
                    "title": booking_addon.addon.title,
                    "title_hi": booking_addon.addon.title_hi,
                    "unit_price": str(booking_addon.unit_price),
                    "quantity": addon_quantity,
                    "total": str(booking_addon.total_price),
                })

            base_snapshot["addons"] = adjusted_addons
            base_snapshot["addon_total"] = str(adjusted_addons_total)
            # Recalculate from the variant/visit base plus the selected add-ons.
            variant_base = Decimal(str(base_snapshot.get("variant_price", "0")))
            visit_fee = Decimal(str(base_snapshot.get("visit_fee", "0")))
            unit_subtotal = variant_base + visit_fee + adjusted_addons_total
            unit_tax = unit_subtotal * Decimal("0.18")
            line_subtotal = unit_subtotal * quantity
            line_tax = unit_tax * quantity
            line_total = line_subtotal + line_tax

            base_snapshot.update({
                "cart_item_id": item.id,
                "quantity": quantity,
                "unit_subtotal": str(unit_subtotal),
                "unit_tax": str(unit_tax),
                "subtotal": str(line_subtotal),
                "tax": str(line_tax),
                "total": str(line_total),
                "currency": "INR",
            })
            booking.pricing_snapshot = base_snapshot
            booking.save(update_fields=["pricing_snapshot", "updated_at"])

            OrderItem.objects.create(
                order=order,
                booking=booking,
                quantity=quantity,
                service_snapshot={
                    "service_id": item.service_id,
                    "service_title": item.service.title,
                    "variant_id": item.variant_id,
                    "variant_title": item.variant.title if item.variant else None,
                    "cart_item_id": item.id,
                    "form_answers": item.form_answers,
                    "category_answers": item.category_answers,
                    "notes": item.notes,
                },
                pricing_snapshot=base_snapshot,
                line_subtotal=line_subtotal,
                tax_amount=line_tax,
                line_total=line_total,
            )
            subtotal += line_subtotal
            tax_total += line_tax
            grand_total += line_total

            # Dispatch is deferred until every OrderItem exists.
            dispatch_results.append({"booking_id": booking.id, "offers_sent": 0})

        order.subtotal = subtotal
        order.tax_amount = tax_total
        order.total_amount = grand_total
        order.save(update_fields=["subtotal", "tax_amount", "total_amount", "updated_at"])

        from apps.bookings.dispatcher import DispatcherService
        order_offers = DispatcherService.dispatch_order(order)
        if dispatch_results:
            dispatch_results[0]["offers_sent"] = len(order_offers)

        cart.items.all().delete()
        return Response({
            "order_id": order.id,
            "status": order.status,
            "address_id": order.address_id,
            "currency": order.currency,
            "subtotal": str(order.subtotal),
            "tax_amount": str(order.tax_amount),
            "total_amount": str(order.total_amount),
            "items": [
                {
                    "order_item_id": row.id,
                    "booking_id": row.booking_id,
                    "service": row.service_snapshot,
                    "quantity": row.quantity,
                    "line_total": str(row.line_total),
                }
                for row in order.items.all()
            ],
            "dispatch": dispatch_results,
            "next_step": (
                "Worker offers sent. Track assignment in the order; payment unlocks after every service is assigned."
                if any(row["offers_sent"] for row in dispatch_results)
                else "No single approved worker is currently eligible and available for every service and selected time in this order. The order is waiting for worker assignment."
            ),
        }, status=status.HTTP_201_CREATED)


class CustomerOrderDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, order_id):
        order = get_object_or_404(
            Order.objects.prefetch_related("items__booking__assignment__worker__user"),
            pk=order_id,
            customer=request.user,
        )
        items = []
        for row in order.items.all():
            booking = row.booking
            assignment = getattr(booking, "assignment", None)
            items.append({
                "order_item_id": row.id,
                "booking_id": booking.id,
                "service": row.service_snapshot,
                "booking_status": booking.status,
                "scheduled_at": booking.scheduled_at,
                "worker": (
                    {
                        "id": assignment.worker_id,
                        "name": assignment.worker.user.name or assignment.worker.user.phone,
                    }
                    if assignment else None
                ),
                "quantity": row.quantity,
                "line_total": str(row.line_total),
            })
        if order.items.exists() and all(row["booking_status"] == Booking.Status.ASSIGNED for row in items):
            if order.status != Order.Status.AWAITING_PAYMENT:
                order.status = Order.Status.AWAITING_PAYMENT
                order.save(update_fields=["status", "updated_at"])
        return Response({
            "id": order.id,
            "status": order.status,
            "currency": order.currency,
            "subtotal": str(order.subtotal),
            "tax_amount": str(order.tax_amount),
            "total_amount": str(order.total_amount),
            "items": items,
            "ready_for_payment": order.status == Order.Status.AWAITING_PAYMENT,
        })


class CustomerOrderListView(APIView):
    """List the authenticated customer's multi-service orders."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        orders = Order.objects.filter(customer=request.user).prefetch_related(
            "items__booking"
        ).order_by("-created_at")
        results = []
        for order in orders:
            statuses = [row.booking.status for row in order.items.all()]
            ready = bool(statuses) and all(
                value == Booking.Status.ASSIGNED for value in statuses
            )
            if ready and order.status == Order.Status.AWAITING_ASSIGNMENT:
                order.status = Order.Status.AWAITING_PAYMENT
                order.save(update_fields=["status", "updated_at"])
            results.append({
                "id": order.id,
                "status": order.status,
                "total_amount": str(order.total_amount),
                "created_at": order.created_at,
                "item_count": len(statuses),
                "ready_for_payment": order.status == Order.Status.AWAITING_PAYMENT,
            })
        return Response(results)


class CustomerCartView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_cart(self, user):
        cart, _ = CustomerCart.objects.get_or_create(customer=user)
        return cart

    def get(self, request):
        cart = self.get_cart(request.user)
        return Response(CustomerCartSerializer(cart, context={"request": request}).data)

    def post(self, request):
        cart = self.get_cart(request.user)
        serializer = CartItemSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        # Once an address is selected, only allow services available in that
        # address's city to be added to the cart.
        if cart.address:
            try:
                check_service_available(
                    service=serializer.validated_data["service"],
                    address=cart.address,
                    audience="all",
                )
            except ServiceUnavailableError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        serializer.save(cart=cart)
        return Response(
            CustomerCartSerializer(cart, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    def patch(self, request):
        cart = self.get_cart(request.user)
        if "address_id" in request.data:
            address_id = request.data.get("address_id")
            if address_id in (None, ""):
                cart.address = None
            else:
                address = get_object_or_404(
                    Address.objects.select_related("zone__city"),
                    pk=address_id,
                    user=request.user,
                    deleted_at__isnull=True,
                )
                # Changing Jaipur to another city must not leave unavailable
                # services silently attached to the cart.
                for item in cart.items.select_related("service"):
                    try:
                        check_service_available(
                            service=item.service,
                            address=address,
                            audience="all",
                        )
                    except ServiceUnavailableError as exc:
                        return Response(
                            {
                                "detail": str(exc),
                                "unavailable_cart_item_id": item.id,
                                "service_id": item.service_id,
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                cart.address = address
            cart.save(update_fields=["address", "updated_at"])
        return Response(CustomerCartSerializer(cart, context={"request": request}).data)


class CustomerCartItemView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_item(self, request, item_id):
        cart = get_object_or_404(CustomerCart, customer=request.user)
        return get_object_or_404(CartItem, cart=cart, pk=item_id)

    def patch(self, request, item_id):
        item = self.get_item(request, item_id)
        serializer = CartItemSerializer(
            item, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        if item.cart.address:
            try:
                check_service_available(
                    service=serializer.validated_data.get("service", item.service),
                    address=item.cart.address,
                    audience="all",
                )
            except ServiceUnavailableError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(CustomerCartSerializer(item.cart, context={"request": request}).data)

    def delete(self, request, item_id):
        item = self.get_item(request, item_id)
        cart = item.cart
        item.delete()
        return Response(CustomerCartSerializer(cart, context={"request": request}).data)
