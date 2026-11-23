from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("bookings", "0029_quote_worker_payout_approval")]

    operations = [
        migrations.AlterField(
            model_name="bookingquote",
            name="status",
            field=models.CharField(choices=[("pending_admin", "Awaiting AIRway payout approval"), ("pending_customer", "Awaiting customer approval"), ("accepted", "Accepted"), ("rejected", "Rejected"), ("superseded", "Superseded by a revised quote")], db_index=True, default="pending_customer", max_length=24),
        ),
        migrations.AddField(
            model_name="bookingquote",
            name="repair_started_at",
            field=models.DateTimeField(blank=True, help_text="Set only after the customer has paid the accepted inspection estimate.", null=True),
        ),
    ]
