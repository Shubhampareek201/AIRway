from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0024_pricing_configuration_constraints"),
    ]

    operations = [
        migrations.AddField(model_name="service", name="estimated_gateway_fee_percent", field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
        migrations.AddField(model_name="historicalservice", name="estimated_gateway_fee_percent", field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
        migrations.AddField(model_name="service", name="discount_reserve_percent", field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
        migrations.AddField(model_name="historicalservice", name="discount_reserve_percent", field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
        migrations.AddField(model_name="service", name="rewards_reserve_percent", field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
        migrations.AddField(model_name="historicalservice", name="rewards_reserve_percent", field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
        migrations.AddField(model_name="service", name="refund_reserve_percent", field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
        migrations.AddField(model_name="historicalservice", name="refund_reserve_percent", field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
        migrations.AddField(model_name="service", name="rework_reserve_percent", field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
        migrations.AddField(model_name="historicalservice", name="rework_reserve_percent", field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
        migrations.AddField(model_name="service", name="other_variable_cost_per_booking", field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
        migrations.AddField(model_name="historicalservice", name="other_variable_cost_per_booking", field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
        migrations.AddField(model_name="service", name="minimum_contribution_floor", field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
        migrations.AddField(model_name="historicalservice", name="minimum_contribution_floor", field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
        migrations.AddField(model_name="service", name="target_contribution_margin_percent", field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
        migrations.AddField(model_name="historicalservice", name="target_contribution_margin_percent", field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
        migrations.AddConstraint(
            model_name="service",
            constraint=models.CheckConstraint(
                condition=models.Q(("estimated_gateway_fee_percent__isnull", True)) | (models.Q(("estimated_gateway_fee_percent__gte", 0)) & models.Q(("estimated_gateway_fee_percent__lte", 100))),
                name="svc_gateway_fee_pct_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="service",
            constraint=models.CheckConstraint(
                condition=models.Q(("discount_reserve_percent__isnull", True)) | (models.Q(("discount_reserve_percent__gte", 0)) & models.Q(("discount_reserve_percent__lte", 100))),
                name="svc_discount_reserve_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="service",
            constraint=models.CheckConstraint(
                condition=models.Q(("rewards_reserve_percent__isnull", True)) | (models.Q(("rewards_reserve_percent__gte", 0)) & models.Q(("rewards_reserve_percent__lte", 100))),
                name="svc_rewards_reserve_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="service",
            constraint=models.CheckConstraint(
                condition=models.Q(("refund_reserve_percent__isnull", True)) | (models.Q(("refund_reserve_percent__gte", 0)) & models.Q(("refund_reserve_percent__lte", 100))),
                name="svc_refund_reserve_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="service",
            constraint=models.CheckConstraint(
                condition=models.Q(("rework_reserve_percent__isnull", True)) | (models.Q(("rework_reserve_percent__gte", 0)) & models.Q(("rework_reserve_percent__lte", 100))),
                name="svc_rework_reserve_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="service",
            constraint=models.CheckConstraint(
                condition=models.Q(("other_variable_cost_per_booking__isnull", True)) | models.Q(("other_variable_cost_per_booking__gte", 0)),
                name="svc_other_cost_nonneg",
            ),
        ),
        migrations.AddConstraint(
            model_name="service",
            constraint=models.CheckConstraint(
                condition=models.Q(("minimum_contribution_floor__isnull", True)) | models.Q(("minimum_contribution_floor__gte", 0)),
                name="svc_min_contribution_nonneg",
            ),
        ),
        migrations.AddConstraint(
            model_name="service",
            constraint=models.CheckConstraint(
                condition=models.Q(("target_contribution_margin_percent__isnull", True)) | (models.Q(("target_contribution_margin_percent__gte", 0)) & models.Q(("target_contribution_margin_percent__lte", 100))),
                name="svc_target_margin_range",
            ),
        ),
    ]
