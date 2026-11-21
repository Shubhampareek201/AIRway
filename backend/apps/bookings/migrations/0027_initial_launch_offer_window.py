from django.db import migrations, models


def extend_default_offer_window(apps, schema_editor):
    DispatchConfiguration = apps.get_model("bookings", "DispatchConfiguration")
    # Upgrade installations still using the original five-minute default,
    # while preserving any value an administrator has deliberately configured.
    DispatchConfiguration.objects.filter(
        pk=1,
        offer_expiry_minutes=5,
    ).update(offer_expiry_minutes=30)


def restore_previous_default(apps, schema_editor):
    DispatchConfiguration = apps.get_model("bookings", "DispatchConfiguration")
    DispatchConfiguration.objects.filter(
        pk=1,
        offer_expiry_minutes=30,
    ).update(offer_expiry_minutes=5)


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0026_bookingdisputehistory"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dispatchconfiguration",
            name="offer_expiry_minutes",
            field=models.PositiveSmallIntegerField(default=30),
        ),
        migrations.RunPython(
            extend_default_offer_window,
            restore_previous_default,
        ),
    ]
