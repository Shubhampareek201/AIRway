from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0010_service_otp"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("awaiting_assignment", "Awaiting Assignment"),
                    ("awaiting_payment", "Awaiting Advance Payment"),
                    ("advance_paid", "Advance Paid"),
                    ("in_progress", "In Progress"),
                    ("awaiting_balance", "Awaiting Balance"),
                    ("paid", "Paid"),
                    ("partially_cancelled", "Partially Cancelled"),
                    ("cancelled", "Cancelled"),
                ],
                db_index=True,
                default="awaiting_assignment",
                max_length=24,
            ),
        ),
    ]
