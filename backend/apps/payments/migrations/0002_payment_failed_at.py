# Generated migration to add failed_at field to Payment model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='failed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='historicalpayment',
            name='failed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]