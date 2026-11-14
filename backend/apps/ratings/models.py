from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models

from apps.bookings.models import Booking


class BookingRating(models.Model):
    rating_type = models.CharField(
        max_length=20,
        choices=[
            ('customer', 'Customer Rating'),
            ('worker', 'Worker Rating'),
        ],
    )
    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name='ratings',
    )
    rater = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='given_ratings',
    )
    rated = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_ratings',
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['booking', 'rater'],
                name='unique_booking_rating_per_user'
            ),
        ]

    def __str__(self):
        return f'{self.get_rating_type_display()} - {self.rating}/5 for {self.rated.phone}'


class RatingSummary(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='rating_summary',
    )
    average_rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0
    )
    total_ratings = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-average_rating']

    def __str__(self):
        return f'{self.user.phone}: {self.average_rating}/5 ({self.total_ratings} ratings)'

    def update_stats(self):
        ratings = BookingRating.objects.filter(rated=self.user)
        if ratings.exists():
            total = ratings.count()
            avg = sum(r.rating for r in ratings) / total
            self.average_rating = round(avg, 2)
            self.total_ratings = total
        else:
            self.average_rating = 0
            self.total_ratings = 0
        self.save(update_fields=['average_rating', 'total_ratings'])