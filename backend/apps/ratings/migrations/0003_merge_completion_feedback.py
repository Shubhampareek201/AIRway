from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("ratings", "0002_alter_bookingrating_rating"),
        ("ratings", "0002_bookingcompletionfeedback"),
    ]

    operations = []
