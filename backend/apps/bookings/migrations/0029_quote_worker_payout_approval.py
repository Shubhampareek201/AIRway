from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0028_booking_worker_payout_snapshot"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(model_name="bookingquote", name="worker_payout_amount", field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
        migrations.AddField(model_name="bookingquote", name="payout_approval_note", field=models.TextField(blank=True)),
        migrations.AddField(model_name="bookingquote", name="payout_approved_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="bookingquote", name="payout_approved_by", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="approved_booking_quote_payouts", to=settings.AUTH_USER_MODEL)),
        migrations.AlterField(model_name="bookingquote", name="status", field=models.CharField(choices=[("pending_admin", "Awaiting AIRway payout approval"), ("pending_customer", "Awaiting customer approval"), ("accepted", "Accepted"), ("rejected", "Rejected"), ("superseded", "Superseded by a revised quote")], db_index=True, default="pending_admin", max_length=24)),
    ]
