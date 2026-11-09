from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0009_alter_workeroffer_booking"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("awaiting_assignment", "Awaiting Assignment"),
                    ("awaiting_payment", "Awaiting Payment"),
                    ("awaiting_service", "Awaiting Service"),
                    ("in_progress", "In Progress"),
                    ("awaiting_final_payment", "Awaiting Final Payment"),
                    ("completed", "Completed"),
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
