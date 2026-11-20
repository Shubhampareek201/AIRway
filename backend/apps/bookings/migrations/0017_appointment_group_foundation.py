import django.db.models.deletion
from django.db import migrations, models


def backfill_appointment_groups(apps, schema_editor):
    Order = apps.get_model("bookings", "Order")
    AppointmentGroup = apps.get_model("bookings", "AppointmentGroup")
    Booking = apps.get_model("bookings", "Booking")
    db = schema_editor.connection.alias

    for order in Order.objects.using(db).all().iterator():
        items = list(
            order.items.using(db).select_related("booking").order_by("created_at", "id")
        )
        if not items:
            continue

        scheduling = (order.metadata or {}).get("scheduling_v1", {})
        if scheduling.get("mode") == "same_appointment":
            scheduled_at = scheduling.get("shared_appointment_at") or items[0].booking.scheduled_at
            group = AppointmentGroup.objects.using(db).create(
                order_id=order.pk,
                group_number=1,
                scheduled_at=scheduled_at,
            )
            Booking.objects.using(db).filter(
                pk__in=[item.booking_id for item in items]
            ).update(appointment_group_id=group.pk)
            continue

        for index, item in enumerate(items, start=1):
            group = AppointmentGroup.objects.using(db).create(
                order_id=order.pk,
                group_number=index,
                scheduled_at=item.booking.scheduled_at,
            )
            Booking.objects.using(db).filter(pk=item.booking_id).update(
                appointment_group_id=group.pk
            )


def reverse_backfill_appointment_groups(apps, schema_editor):
    Booking = apps.get_model("bookings", "Booking")
    AppointmentGroup = apps.get_model("bookings", "AppointmentGroup")
    db = schema_editor.connection.alias
    Booking.objects.using(db).update(appointment_group=None)
    AppointmentGroup.objects.using(db).all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0016_bookingassignment_live_location"),
    ]

    operations = [
        migrations.CreateModel(
            name="AppointmentGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("group_number", models.PositiveSmallIntegerField()),
                ("scheduled_at", models.DateTimeField()),
                ("customer_message", models.CharField(blank=True, help_text="One optional message shared with the worker handling this appointment.", max_length=500)),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="appointment_groups", to="bookings.order")),
            ],
            options={
                "ordering": ["group_number", "id"],
            },
        ),
        migrations.AddField(
            model_name="booking",
            name="appointment_group",
            field=models.ForeignKey(
                blank=True,
                help_text="Appointment grouping for multi-service orders; null for legacy standalone bookings.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="bookings",
                to="bookings.appointmentgroup",
            ),
        ),
        migrations.AddConstraint(
            model_name="appointmentgroup",
            constraint=models.UniqueConstraint(
                fields=("order", "group_number"),
                name="unique_order_appointment_group_number",
            ),
        ),
        migrations.RunPython(
            backfill_appointment_groups,
            reverse_backfill_appointment_groups,
        ),
    ]
