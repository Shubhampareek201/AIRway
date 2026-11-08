from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0013_category_audience_options"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="category",
            name="audience_options",
        ),
        migrations.CreateModel(
            name="CategoryAudienceOption",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("audience", models.CharField(choices=[("men", "Men"), ("women", "Women"), ("both", "Both / Unisex")], max_length=10)),
                ("title", models.CharField(max_length=80)),
                ("subtitle", models.CharField(blank=True, max_length=180)),
                ("image", models.ImageField(upload_to="category_audiences/")),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="audience_options", to="catalog.category")),
            ],
            options={"ordering": ["sort_order", "id"]},
        ),
        migrations.AddConstraint(
            model_name="categoryaudienceoption",
            constraint=models.UniqueConstraint(fields=("category", "audience"), name="unique_category_audience_option"),
        ),
    ]
