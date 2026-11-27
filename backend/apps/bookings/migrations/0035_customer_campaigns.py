# Customer campaign configuration and order-level redemption ledger.
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0034_alter_booking_pricing_snapshot_and_more"),
        ("catalog", "0029_alter_historicaladdon_pricing_change_reason_and_more"),
        ("core", "0005_alter_zone_coverage_radius_meters"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="CustomerCampaign",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=False)),
                ("booking_sequence", models.CharField(choices=[("first", "First paid booking"), ("second", "Second paid booking"), ("any", "Any eligible paid booking")], default="any", max_length=12)),
                ("discount_type", models.CharField(choices=[("fixed", "Fixed amount"), ("percentage", "Percentage")], default="fixed", max_length=12)),
                ("discount_value", models.DecimalField(decimal_places=2, max_digits=10)),
                ("max_discount_amount", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("minimum_subtotal", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("starts_at", models.DateTimeField(blank=True, null=True)),
                ("ends_at", models.DateTimeField(blank=True, null=True)),
                ("budget_amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("budget_reserved", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("budget_spent", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("max_redemptions_per_customer", models.PositiveIntegerField(default=1)),
                ("max_total_redemptions", models.PositiveIntegerField(blank=True, null=True)),
                ("allow_stacking", models.BooleanField(default=False)),
                ("priority", models.PositiveIntegerField(default=100)),
                ("eligible_services", models.ManyToManyField(blank=True, related_name="discount_campaigns", to="catalog.service")),
                ("eligible_zones", models.ManyToManyField(blank=True, related_name="discount_campaigns", to="core.zone")),
            ],
            options={"ordering": ["priority", "-created_at"]},
        ),
        migrations.AddConstraint(model_name="customercampaign", constraint=models.CheckConstraint(condition=models.Q(("discount_value__gt", 0)), name="campaign_discount_value_positive")),
        migrations.AddConstraint(model_name="customercampaign", constraint=models.CheckConstraint(condition=models.Q(("minimum_subtotal__gte", 0)), name="campaign_min_subtotal_nonneg")),
        migrations.AddConstraint(model_name="customercampaign", constraint=models.CheckConstraint(condition=models.Q(("budget_amount__gt", 0)), name="campaign_budget_positive")),
        migrations.AddConstraint(model_name="customercampaign", constraint=models.CheckConstraint(condition=models.Q(("budget_reserved__gte", 0), ("budget_spent__gte", 0)), name="campaign_budget_counters_nonneg")),
        migrations.AddConstraint(model_name="customercampaign", constraint=models.CheckConstraint(condition=models.Q(("budget_reserved__lte", models.F("budget_amount") - models.F("budget_spent"))), name="campaign_budget_within_limit")),
        migrations.AddConstraint(model_name="customercampaign", constraint=models.CheckConstraint(condition=models.Q(("max_discount_amount__isnull", True), ("max_discount_amount__gt", 0), _connector="OR"), name="campaign_discount_cap_positive")),
        migrations.AddConstraint(model_name="customercampaign", constraint=models.CheckConstraint(condition=models.Q(("max_redemptions_per_customer__gte", 1)), name="campaign_customer_limit_positive")),
        migrations.AddConstraint(model_name="customercampaign", constraint=models.CheckConstraint(condition=models.Q(("max_total_redemptions__isnull", True), ("max_total_redemptions__gte", 1), _connector="OR"), name="campaign_total_limit_positive")),
        migrations.CreateModel(
            name="CampaignRedemption",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("discount_amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("status", models.CharField(choices=[("reserved", "Reserved"), ("redeemed", "Redeemed"), ("released", "Released"), ("refunded", "Refunded")], db_index=True, default="reserved", max_length=12)),
                ("reserved_at", models.DateTimeField(auto_now_add=True)),
                ("redeemed_at", models.DateTimeField(blank=True, null=True)),
                ("released_at", models.DateTimeField(blank=True, null=True)),
                ("release_reason", models.CharField(blank=True, max_length=160)),
                ("campaign", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="redemptions", to="bookings.customercampaign")),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="campaign_redemptions", to=settings.AUTH_USER_MODEL)),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="campaign_redemptions", to="bookings.order")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(model_name="campaignredemption", constraint=models.UniqueConstraint(fields=("campaign", "order"), name="unique_campaign_redemption_per_order")),
        migrations.AddConstraint(model_name="campaignredemption", constraint=models.CheckConstraint(condition=models.Q(("discount_amount__gt", 0)), name="campaign_redemption_amount_positive")),
    ]
