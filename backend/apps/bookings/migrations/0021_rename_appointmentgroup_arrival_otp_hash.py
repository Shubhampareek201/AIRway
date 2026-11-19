from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0020_appointmentgroup_arrival_otp"),
    ]

    operations = [
        migrations.RenameField(
            model_name="appointmentgroup",
            old_name="arrival_otp",
            new_name="arrival_otp_hash",
        ),
        migrations.AlterField(
            model_name="appointmentgroup",
            name="arrival_otp_hash",
            field=models.CharField(blank=True, max_length=128),
        ),
    ]
