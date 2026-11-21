import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def populate_refund_idempotency_keys(apps, schema_editor):
    PaymentRefund = apps.get_model("payments", "PaymentRefund")
    for refund in PaymentRefund.objects.only("pk").iterator():
        PaymentRefund.objects.filter(pk=refund.pk).update(
            idempotency_key=f"legacy-refund-{refund.pk}"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0008_extra_work_payments"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="paymentrefund",
            name="idempotency_key",
            field=models.CharField(max_length=100, null=True, editable=False),
        ),
        migrations.RunPython(
            populate_refund_idempotency_keys,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="paymentrefund",
            name="idempotency_key",
            field=models.CharField(
                default=uuid.uuid4, editable=False, max_length=100, unique=True
            ),
        ),
        migrations.AddField(
            model_name="paymentrefund",
            name="requested_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="issued_payment_refunds",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="paymentrefund",
            name="admin_note",
            field=models.TextField(blank=True),
        ),
        migrations.RemoveConstraint(
            model_name="paymentrefund",
            name="unique_payment_refund_booking",
        ),
        migrations.AlterModelOptions(
            name="paymentrefund",
            options={
                "ordering": ["-created_at"],
                "permissions": [
                    (
                        "issue_partial_paymentrefund",
                        "Can issue partial payment refunds",
                    )
                ],
            },
        ),
    ]
