from django.db import migrations


def correct_beauty_audience_metadata(apps, schema_editor):
    Service = apps.get_model("catalog", "Service")

    # The service title is explicitly men's-only; it must not appear in Both
    # or Women's Beauty simply because its legacy audience was set to "all".
    Service.objects.filter(
        title="Men's Hair Wash",
        category__parent__slug="beauty",
        audience="all",
    ).update(audience="men")

    # A bridal facial is an occasion-specific women's service, not a generic
    # unisex facial. Other facial services retain their existing audience.
    Service.objects.filter(
        title="Bridal Facial",
        category__parent__slug="beauty",
        audience="all",
    ).update(audience="women")


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0011_formfield_visibility_rules"),
    ]

    operations = [
        migrations.RunPython(
            correct_beauty_audience_metadata,
            migrations.RunPython.noop,
        ),
    ]
