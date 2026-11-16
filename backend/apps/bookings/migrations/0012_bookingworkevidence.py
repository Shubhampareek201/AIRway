import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0011_bookingquote"),
        ("workers", "0006_workerprofile_gps_coordinates"),
    ]

    operations = [
        migrations.CreateModel(
            name="BookingWorkEvidence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("stage", models.CharField(choices=[("before", "Before work"), ("after", "After work")], db_index=True, max_length=8)),
                ("image_path", models.CharField(max_length=500)),
                ("note", models.CharField(blank=True, max_length=500)),
                ("booking", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="work_evidence", to="bookings.booking")),
                ("worker", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="work_evidence", to="workers.workerprofile")),
            ],
            options={
                "ordering": ["created_at", "id"],
                "indexes": [models.Index(fields=["booking", "stage"], name="booking_evidence_stage_idx")],
            },
        ),
    ]
