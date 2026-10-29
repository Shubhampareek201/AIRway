from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Address
from .models import WorkerService, WorkerZone


class NearbyWorkersView(APIView):
    """Return approved, online workers assigned to the customer's saved service zone."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        address_id = request.query_params.get("address_id")
        addresses = Address.objects.filter(
            user=request.user,
            deleted_at__isnull=True,
        ).select_related("zone")

        if address_id:
            address = addresses.filter(pk=address_id).first()
            if address is None:
                return Response({"detail": "Saved address not found."}, status=404)
        else:
            address = addresses.filter(is_default=True).first() or addresses.order_by("-id").first()

        if address is None:
            return Response({"count": 0, "results": [], "message": "Add a saved address to check local partner availability."})

        if not address.zone_id or not address.zone.is_active:
            return Response({"count": 0, "results": [], "message": "A supported service zone has not been confirmed for this address."})

        zone_links = (
            WorkerZone.objects.filter(
                zone_id=address.zone_id,
                worker__status="approved",
                worker__is_online=True,
            )
            .select_related("worker__user")
            .distinct()
        )

        results = []
        seen_worker_ids = set()
        for zone_link in zone_links:
            worker = zone_link.worker
            if worker.pk in seen_worker_ids:
                continue

            service_rows = (
                WorkerService.objects.filter(
                    worker=worker,
                    service__is_active=True,
                    service__category__is_active=True,
                )
                .select_related("service")
                .order_by("service__sort_order", "service__title")
            )
            service_titles = list(service_rows.values_list("service__title", flat=True))
            if not service_titles:
                continue

            user = worker.user
            name = (user.get_full_name() or "").strip() or "Verified partner"
            rating = getattr(worker, "rating", None)
            results.append(
                {
                    "id": worker.pk,
                    "name": name,
                    "rating": float(rating) if rating is not None else None,
                    "services": service_titles,
                    "is_online": True,
                }
            )
            seen_worker_ids.add(worker.pk)

        results.sort(key=lambda item: (item["rating"] is None, -(item["rating"] or 0)))
        return Response({"count": len(results), "results": results})
