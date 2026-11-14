from django.db.models import Avg, Count
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.ratings.models import BookingRating, RatingSummary


@receiver(post_save, sender=BookingRating)
def update_rating_summary(sender, instance, created, **kwargs):
    if created:
        # Both customer and worker ratings contribute to the person being rated.
        summary, _ = RatingSummary.objects.get_or_create(user=instance.rated)
        summary.update_stats()
        if instance.rating_type == "customer":
            # Keep the worker aggregate used by discovery and dispatch in sync
            # with authoritative customer-to-worker ratings.
            from apps.workers.models import WorkerProfile
            stats = BookingRating.objects.filter(
                rated=instance.rated,
                rating_type="customer",
            ).aggregate(average=Avg("rating"), total=Count("id"))
            WorkerProfile.objects.filter(user=instance.rated).update(
                rating_avg=stats["average"] or 0,
                rating_count=stats["total"] or 0,
            )
