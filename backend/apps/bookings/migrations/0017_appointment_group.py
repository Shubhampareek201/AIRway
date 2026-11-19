from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0016_bookingassignment_live_location"),
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AppointmentGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("category_slug_snapshot", models.SlugField(max_length=100)),
                ("category_title_snapshot", models.CharField(max_length=150)),
                ("scheduled_at", models.DateTimeField()),
                ("customer_message", models.CharField(blank=True, max_length=500)),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="appointment_groups", to="bookings.order")),
                ("root_category", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="appointment_groups", to="catalog.category")),
            ],
            options={
                "ordering": ["scheduled_at", "id"],
            },
        ),
        migrations.AddField(
            model_name="booking",
            name="appointment_group",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="bookings", to="bookings.appointmentgroup"),
        ),
        migrations.AddConstraint(
            model_name="appointmentgroup",
            constraint=models.UniqueConstraint(fields=("order", "root_category"), name="unique_order_root_appointment_group"),
        ),
        migrations.AddIndex(
            model_name="appointmentgroup",
            index=models.Index(fields=["order", "scheduled_at"], name="appt_group_order_time_idx"),
        ),
    ]
