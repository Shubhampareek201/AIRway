from django.db import migrations, models


def mark_existing_rewards_as_issued(apps, schema_editor):
    Referral = apps.get_model("accounts", "Referral")
    Referral.objects.filter(rewarded=True).update(reward_status="rewarded")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0012_worker_referral_reward_tracking"),
    ]

    operations = [
        migrations.AddField(
            model_name="referral",
            name="reward_status",
            field=models.CharField(
                choices=[
                    ("pending", "Waiting for eligible completed booking"),
                    ("rewarded", "Promotional credits issued"),
                ],
                db_index=True,
                default="pending",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="referral",
            name="reward_booking_id",
            field=models.PositiveBigIntegerField(
                blank=True,
                help_text="Booking whose original service subtotal qualified for the referral reward.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="referral",
            name="reward_original_service_charge",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Original pre-tax, pre-campaign-discount service subtotal at qualification.",
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="referral",
            name="applied_ip",
            field=models.GenericIPAddressField(
                blank=True,
                help_text="Signup/application IP retained for referral abuse review; shared IP alone is not disqualifying.",
                null=True,
            ),
        ),
        migrations.RunPython(mark_existing_rewards_as_issued, migrations.RunPython.noop),
    ]
