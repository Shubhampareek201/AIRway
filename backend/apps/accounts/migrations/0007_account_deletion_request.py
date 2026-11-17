# Generated for AIRway account deletion request tracking.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_favorite_service"),
    ]

    operations = [
        migrations.CreateModel(
            name="AccountDeletionRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(choices=[
                    ("requested", "Requested"),
                    ("under_review", "Under review"),
                    ("rejected", "Rejected"),
                    ("completed", "Completed"),
                    ("cancelled", "Cancelled"),
                ], db_index=True, default="requested", max_length=20)),
                ("reason", models.TextField(blank=True)),
                ("has_active_bookings", models.BooleanField(default=False)),
                ("active_booking_count", models.PositiveIntegerField(default=0)),
                ("admin_notes", models.TextField(blank=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="account_deletion_requests",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="accountdeletionrequest",
            index=models.Index(fields=["user", "status"], name="accounts_ac_user_i_6a2f90_idx"),
        ),
    ]
