from django.db import migrations


PREMIUM_CAR_MAKES = {
    "BMW": [
        ("2 Series Gran Coupe", "Sedan"), ("3 Series", "Sedan"),
        ("5 Series", "Sedan"), ("X1", "Compact SUV"),
        ("X3", "SUV – 5 Seater"), ("X5", "Luxury SUV"),
        ("X7", "Luxury SUV"),
    ],
    "Audi": [
        ("A4", "Sedan"), ("A6", "Sedan"), ("Q3", "Compact SUV"),
        ("Q5", "SUV – 5 Seater"), ("Q7", "Luxury SUV"),
        ("Q8", "Luxury SUV"),
    ],
    "Mercedes-Benz": [
        ("A-Class Limousine", "Sedan"), ("C-Class", "Sedan"),
        ("E-Class", "Sedan"), ("GLA", "Compact SUV"),
        ("GLC", "SUV – 5 Seater"), ("GLE", "Luxury SUV"),
        ("GLS", "Luxury SUV"),
    ],
}


def seed_premium_vehicle_makes(apps, schema_editor):
    VehicleMake = apps.get_model("catalog", "VehicleMake")
    VehicleModel = apps.get_model("catalog", "VehicleModel")

    for make_order, (make_name, models) in enumerate(PREMIUM_CAR_MAKES.items()):
        make, _ = VehicleMake.objects.get_or_create(
            vehicle_type="car",
            name=make_name,
            defaults={"sort_order": make_order, "is_active": True},
        )
        for model_order, (model_name, vehicle_class) in enumerate(models, start=1):
            VehicleModel.objects.get_or_create(
                make=make,
                name=model_name,
                defaults={
                    "vehicle_class": vehicle_class,
                    "sort_order": model_order,
                    "is_active": True,
                },
            )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0018_seed_vehicle_catalogue"),
    ]

    operations = [
        migrations.RunPython(seed_premium_vehicle_makes, migrations.RunPython.noop),
    ]
