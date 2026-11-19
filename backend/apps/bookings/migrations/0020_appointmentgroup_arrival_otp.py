from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0019_customercart_group_messages"),
    ]

    operations = [
        migrations.AddField(
            model_name="appointmentgroup",
            name="arrival_otp_hash",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name="appointmentgroup",
            name="arrival_otp_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="appointmentgroup",
            name="arrival_otp_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="appointmentgroup",
            name="arrival_otp_attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="appointmentgroup",
            name="arrival_otp_locked_until",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
