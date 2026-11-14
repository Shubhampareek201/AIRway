from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.ratings.models import BookingRating, RatingSummary


@receiver(post_save, sender=BookingRating)
def update_rating_summary(sender, instance, created, **kwargs):
    if created:
        # Both customer and worker ratings contribute to the person being rated.
        summary, _ = RatingSummary.objects.get_or_create(user=instance.rated)
        summary.update_stats()
