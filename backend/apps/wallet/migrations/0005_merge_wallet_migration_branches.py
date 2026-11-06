from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("wallet", "0002_wallettransaction_razorpay_payment_id"),
        ("wallet", "0004_one_active_reservation"),
    ]

    operations = []
