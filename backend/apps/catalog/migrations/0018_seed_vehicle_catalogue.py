from django.db import migrations


CAR_MAKES = {
    "Maruti Suzuki": [
        ("Alto K10", "Hatchback"), ("WagonR", "Hatchback"),
        ("Swift", "Hatchback"), ("Baleno", "Hatchback"),
        ("Dzire", "Sedan"), ("Brezza", "Compact SUV"),
        ("Ertiga", "MUV / MPV"), ("Grand Vitara", "SUV – 5 Seater"),
    ],
    "Hyundai": [
        ("Grand i10 Nios", "Hatchback"), ("i20", "Hatchback"),
        ("Aura", "Sedan"), ("Exter", "Compact SUV"),
        ("Venue", "Compact SUV"), ("Creta", "SUV – 5 Seater"),
        ("Alcazar", "SUV – 7 Seater"),
    ],
    "Tata": [
        ("Tiago", "Hatchback"), ("Tigor", "Sedan"), ("Altroz", "Hatchback"),
        ("Punch", "Compact SUV"), ("Nexon", "Compact SUV"),
        ("Harrier", "SUV – 5 Seater"), ("Safari", "SUV – 7 Seater"),
    ],
    "Honda": [
        ("Amaze", "Sedan"), ("City", "Sedan"), ("Elevate", "SUV – 5 Seater"),
    ],
    "Toyota": [
        ("Glanza", "Hatchback"), ("Urban Cruiser Taisor", "Compact SUV"),
        ("Urban Cruiser Hyryder", "SUV – 5 Seater"),
        ("Innova Crysta", "MUV / MPV"), ("Innova Hycross", "MUV / MPV"),
        ("Fortuner", "Luxury SUV"),
    ],
    "Mahindra": [
        ("XUV 3XO", "Compact SUV"), ("Thar", "SUV – 5 Seater"),
        ("Scorpio-N", "SUV – 7 Seater"), ("XUV700", "SUV – 7 Seater"),
        ("Bolero", "MUV / MPV"),
    ],
    "Kia": [
        ("Sonet", "Compact SUV"), ("Seltos", "SUV – 5 Seater"),
        ("Carens", "MUV / MPV"),
    ],
    "Renault": [
        ("Kwid", "Hatchback"), ("Kiger", "Compact SUV"), ("Triber", "MUV / MPV"),
    ],
    "Nissan": [("Magnite", "Compact SUV")],
    "MG": [
        ("Comet EV", "Hatchback"), ("Astor", "SUV – 5 Seater"),
        ("Hector", "SUV – 5 Seater"),
    ],
    "Skoda": [
        ("Kylaq", "Compact SUV"), ("Slavia", "Sedan"),
        ("Kushaq", "SUV – 5 Seater"), ("Kodiaq", "Luxury SUV"),
    ],
    "Volkswagen": [
        ("Virtus", "Sedan"), ("Taigun", "SUV – 5 Seater"),
        ("Tiguan", "Luxury SUV"),
    ],
}

BIKE_MAKES = {
    "Honda": [("Activa", "Scooter"), ("Dio", "Scooter"), ("Shine", "Motorcycle"), ("SP 125", "Motorcycle")],
    "TVS": [("Jupiter", "Scooter"), ("Ntorq", "Scooter"), ("Apache RTR", "Motorcycle"), ("Raider", "Motorcycle")],
    "Hero": [("Splendor Plus", "Motorcycle"), ("HF Deluxe", "Motorcycle"), ("Xpulse 200", "Motorcycle")],
    "Bajaj": [("Pulsar", "Motorcycle"), ("Platina", "Motorcycle"), ("Chetak", "Scooter")],
    "Royal Enfield": [("Classic 350", "Motorcycle"), ("Hunter 350", "Motorcycle"), ("Bullet 350", "Motorcycle")],
    "Suzuki": [("Access 125", "Scooter"), ("Burgman Street", "Scooter"), ("Gixxer", "Motorcycle")],
    "Yamaha": [("FZ", "Motorcycle"), ("R15", "Motorcycle"), ("Fascino", "Scooter")],
    "Ather": [("450X", "Scooter"), ("Rizta", "Scooter")],
    "Ola Electric": [("S1 Pro", "Scooter"), ("S1 X", "Scooter")],
}


def seed_vehicle_catalogue(apps, schema_editor):
    VehicleMake = apps.get_model("catalog", "VehicleMake")
    VehicleModel = apps.get_model("catalog", "VehicleModel")
    for vehicle_type, makes in (("car", CAR_MAKES), ("bike", BIKE_MAKES)):
        for make_order, (make_name, models) in enumerate(makes.items(), start=1):
            make, _ = VehicleMake.objects.get_or_create(
                vehicle_type=vehicle_type,
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
        ("catalog", "0017_vehicle_catalogue"),
    ]

    operations = [
        migrations.RunPython(seed_vehicle_catalogue, migrations.RunPython.noop),
    ]
