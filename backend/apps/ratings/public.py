from django.db.models import Avg, Count

from apps.ratings.models import BookingRating
from apps.workers.eligibility import mask_personal_contact_details


def customer_reputation_summary(customer):
    """Expose only aggregate feedback workers have submitted about this customer."""
    ratings = BookingRating.objects.filter(
        rated=customer,
        rating_type="worker",
        booking__status="completed",
    )
    stats = ratings.aggregate(average=Avg("rating"), total=Count("id"))
    comments = [
        mask_personal_contact_details(comment)
        for comment in ratings.exclude(comment="").order_by("-created_at").values_list("comment", flat=True)[:3]
    ]
    return {
        "customer_rating_average": round(float(stats["average"]), 2) if stats["average"] is not None else None,
        "customer_rating_count": stats["total"] or 0,
        "customer_rating_comments": comments,
    }
}
