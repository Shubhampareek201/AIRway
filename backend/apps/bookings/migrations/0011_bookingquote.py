import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0010_booking_completion_otp"),
        ("workers", "0006_workerprofile_gps_coordinates"),
    ]

    operations = [
        migrations.CreateModel(
            name="BookingQuote",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("version", models.PositiveIntegerField(default=1)),
                ("line_items", models.JSONField(default=list, help_text="Worker estimate rows: labour, material or other with description, quantity and unit price.")),
                ("labour_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("material_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("other_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("tax_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("total_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("notes", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("pending_customer", "Awaiting customer approval"), ("accepted", "Accepted"), ("rejected", "Rejected"), ("superseded", "Superseded by a revised quote")], db_index=True, default="pending_customer", max_length=24)),
                ("customer_response_note", models.TextField(blank=True)),
                ("responded_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("booking", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="quotes", to="bookings.booking")),
                ("worker", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="booking_quotes", to="workers.workerprofile")),
            ],
            options={
                "ordering": ["-version", "-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="bookingquote",
            constraint=models.UniqueConstraint(fields=("booking", "version"), name="unique_booking_quote_version"),
        ),
        migrations.AddConstraint(
            model_name="bookingquote",
            constraint=models.UniqueConstraint(condition=models.Q(("status", "pending_customer")), fields=("booking",), name="one_pending_quote_per_booking"),
        ),
    ]
