from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.ratings.models import BookingRating, RatingSummary


@receiver(post_save, sender=BookingRating)
def update_rating_summary(sender, instance, created, **kwargs):
    if created:
        if instance.rating_type == 'customer':
            summary, _ = RatingSummary.objects.get_or_create(user=instance.rated)
            summary.update_stats()
        elif instance.rating_type == 'worker':
            summary, _ = RatingSummary.objects.get_or_create(user=instance.rater)
            summary.update_stats()