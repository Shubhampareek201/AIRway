from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("workers", "0004_workerservice_capabilities"),
    ]

    operations = [
        migrations.AddField(
            model_name="workerservice",
            name="experience_years",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Worker-reported experience for this service.",
            ),
        ),
        migrations.AlterField(
            model_name="workerdocument",
            name="doc_type",
            field=models.CharField(
                choices=[
                    ("aadhaar", "Legacy Aadhaar"),
                    ("aadhaar_front", "Aadhaar front"),
                    ("aadhaar_back", "Aadhaar back"),
                    ("id", "Other ID"),
                    ("photo", "Photograph"),
                    ("address_proof", "Address proof"),
                    ("qualification", "Qualification certificate"),
                    ("other", "Other"),
                ],
                max_length=20,
            ),
        ),
    ]
