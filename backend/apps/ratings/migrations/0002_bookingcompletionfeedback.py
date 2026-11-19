import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0020_appointmentgroup_arrival_otp"),
        ("ratings", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BookingCompletionFeedback",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("service_quality", models.PositiveSmallIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)])),
                ("worker_behaviour", models.PositiveSmallIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)])),
                ("satisfaction_level", models.CharField(blank=True, choices=[("very_satisfied", "Very satisfied"), ("satisfied", "Satisfied"), ("neutral", "Neutral"), ("unsatisfied", "Unsatisfied"), ("very_unsatisfied", "Very unsatisfied")], max_length=20)),
                ("comment", models.TextField(blank=True, max_length=1000)),
                ("skipped", models.BooleanField(default=False)),
                ("submitted_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("booking", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="completion_feedback", to="bookings.booking")),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="booking_completion_feedback", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-submitted_at"],
            },
        ),
    ]
