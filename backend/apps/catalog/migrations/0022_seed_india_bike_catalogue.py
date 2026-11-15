from django.db import migrations


# Indian two-wheeler catalogue: commonly owned/current models plus widely seen
# legacy models. VehicleMake/VehicleModel remain the single source of truth used
# by the existing public catalogue APIs and customer saved-vehicle flow.
BIKE_CATALOGUE = {
    "Honda": {
        "Scooter": [
            "Activa", "Activa 6G", "Activa 125", "Dio", "Dio 125", "Grazia",
            "Cliq", "Aviator", "Dunk",
        ],
        "Motorcycle": [
            "Shine 100", "Shine", "Shine 125", "SP 125", "SP160", "Unicorn",
            "Hornet 2.0", "Livo", "X-Blade", "CB200X", "CB300F", "CB300R",
            "CB350", "Hness CB350", "CB350RS", "CBR650R", "NX500",
        ],
    },
    "TVS": {
        "Scooter": [
            "Jupiter", "Jupiter 125", "NTORQ 125", "NTORQ 150", "Scooty Pep Plus",
            "Zest 110", "Wego", "iQube", "iQube S", "iQube ST", "X",
        ],
        "Motorcycle": [
            "XL100", "Radeon", "Sport", "Star City Plus", "Victor", "Apache RTR 160",
            "Apache RTR 160 4V", "Apache RTR 180", "Apache RTR 200 4V",
            "Apache RR 310", "Ronin", "Raider 125", "Radeon",
        ],
    },
    "Suzuki": {
        "Scooter": [
            "Access 125", "Burgman Street", "Burgman Street EX", "Avenis 125",
            "Swish", "Lets",
        ],
        "Motorcycle": [
            "Gixxer", "Gixxer SF", "Gixxer 250", "Gixxer SF 250", "V-Strom SX",
            "V-Strom 800DE", "Hayabusa", "Katana",
        ],
    },
    "Yamaha": {
        "Scooter": [
            "Fascino 125", "Ray ZR 125", "Ray ZR Street Rally", "Aerox 155",
            "Alpha", "Fascino",
        ],
        "Motorcycle": [
            "FZ-FI", "FZ-S FI", "FZ-X", "MT-15", "R15 V4", "R15M",
            "R3", "R7", "R1", "FZ25", "Fazer 25",
        ],
    },
    "Hero": {
        "Scooter": [
            "Pleasure Plus", "Pleasure Plus XTEC", "Destini 110", "Destini 125",
            "Xoom 110", "Xoom 125", "Maestro Edge", "Duet",
        ],
        "Motorcycle": [
            "Splendor Plus", "Splendor Plus XTEC", "Splendor iSmart", "HF Deluxe",
            "HF 100", "Passion Plus", "Passion XTEC", "Glamour", "Glamour XTEC",
            "Super Splendor", "Super Splendor XTEC", "Xtreme 125R", "Xtreme 160R",
            "Xtreme 200S", "Xpulse 200 4V", "Karizma XMR", "Mavrick 440",
        ],
    },
    "Bajaj": {
        "Scooter": ["Chetak", "Chetak 2903", "Chetak 3501", "Chetak 3502"],
        "Motorcycle": [
            "Platina 100", "Platina 110", "CT 110X", "Freedom 125", "Pulsar 125",
            "Pulsar NS125", "Pulsar N150", "Pulsar 150", "Pulsar NS160",
            "Pulsar N160", "Pulsar NS200", "Pulsar N250", "Pulsar F250",
            "Pulsar RS200", "Dominar 250", "Dominar 400", "Avenger Street 160",
            "Avenger Cruise 220",
        ],
    },
    "Ather": {
        "Scooter": ["450S", "450X", "450 Apex", "Rizta", "Rizta S", "Rizta Z"],
        "Motorcycle": [],
    },
    "Ola Electric": {
        "Scooter": ["S1 X", "S1 X+", "S1 Air", "S1 Pro", "S1 Pro+", "Roadster X"],
        "Motorcycle": [],
    },
    "Vida": {
        "Scooter": ["V1", "V1 Plus", "V1 Pro", "V2 Lite", "V2 Plus", "V2 Pro", "VX2"],
        "Motorcycle": [],
    },
    "Vespa": {
        "Scooter": ["ZX 125", "VXL 125", "VXL 150", "SXL 125", "SXL 150", "Elegante 150", "Tech 125"],
        "Motorcycle": [],
    },
    "Aprilia": {
        "Scooter": ["SR 125", "SR 160", "SR 175", "SXR 125", "SXR 160"],
        "Motorcycle": ["RS 457", "RS 660", "Tuono 457", "Tuono 660"],
    },
    "Royal Enfield": {
        "Scooter": [],
        "Motorcycle": [
            "Bullet 350", "Classic 350", "Hunter 350", "Meteor 350", "Goan Classic 350",
            "Himalayan 450", "Scram 440", "Guerrilla 450", "Interceptor 650",
            "Continental GT 650", "Super Meteor 650", "Shotgun 650", "Bear 650",
            "Himalayan 411", "Thunderbird 350", "Thunderbird 500", "Electra 350",
        ],
    },
    "KTM": {
        "Scooter": [],
        "Motorcycle": [
            "Duke 125", "Duke 200", "Duke 250", "Duke 390", "RC 125", "RC 200",
            "RC 390", "Adventure 250", "Adventure 390", "Adventure 390 X",
        ],
    },
    "Kawasaki": {
        "Scooter": [],
        "Motorcycle": [
            "Ninja 300", "Ninja 400", "Ninja 500", "Ninja 650", "Ninja ZX-4R",
            "Ninja ZX-6R", "Ninja ZX-10R", "Ninja H2", "Z650", "Z650RS",
            "Z900", "Z H2", "Versys 650", "Versys 1000", "Vulcan S",
            "W175", "Eliminator",
        ],
    },
    "Triumph": {
        "Scooter": [],
        "Motorcycle": [
            "Speed 400", "Scrambler 400 X", "Thruxton 400", "Speed T4",
            "Bonneville T100", "Bonneville T120", "Street Triple R",
            "Street Triple RS", "Trident 660", "Daytona 660", "Tiger Sport 660",
            "Tiger 900", "Tiger 1200", "Bonneville Bobber",
        ],
    },
    "BMW Motorrad": {
        "Scooter": [],
        "Motorcycle": [
            "G 310 R", "G 310 GS", "G 310 RR", "F 900 R", "F 900 GS",
            "F 850 GS", "S 1000 RR", "S 1000 R", "M 1000 RR", "R 1250 GS",
            "R 1300 GS", "R 18",
        ],
    },
    "Ducati": {
        "Scooter": [],
        "Motorcycle": [
            "Scrambler Icon", "Monster", "Panigale V2", "Panigale V4",
            "Streetfighter V2", "Streetfighter V4", "Multistrada V2",
            "Multistrada V4", "Diavel V4", "Hypermotard 950",
        ],
    },
    "Jawa": {
        "Scooter": [],
        "Motorcycle": ["42", "42 FJ", "42 Bobber", "Perak", "350", "Standard"],
    },
    "Yezdi": {
        "Scooter": [],
        "Motorcycle": ["Roadster", "Scrambler", "Adventure"],
    },
    "Husqvarna": {
        "Scooter": [],
        "Motorcycle": ["Svartpilen 250", "Svartpilen 401", "Vitpilen 250", "Vitpilen 401"],
    },
    "Harley-Davidson": {
        "Scooter": [],
        "Motorcycle": ["X440", "Nightster", "Sportster S", "Fat Boy", "Heritage Classic",
                       "Street Glide", "Road Glide", "Pan America 1250"],
    },
    "Indian Motorcycle": {
        "Scooter": [],
        "Motorcycle": ["Scout", "Scout Bobber", "Chief", "Chief Bobber", "Super Chief",
                       "Chieftain", "Roadmaster", "FTR"],
    },
    "Benelli": {
        "Scooter": [],
        "Motorcycle": ["Imperiale 400", "Leoncino 500", "TRK 502", "TRK 502X", "302S"],
    },
    "Moto Guzzi": {
        "Scooter": [],
        "Motorcycle": ["V7", "V85 TT", "V9 Bobber"],
    },
    "QJMotor": {
        "Scooter": [],
        "Motorcycle": ["SRK 400", "SRK 700", "SRT 550", "SRT 800"],
    },
    "Keeway": {
        "Scooter": [],
        "Motorcycle": ["K-Light 250V", "V302C", "K300 SF", "K300 R"],
    },
}


# Raster brand marks are returned by the existing serializer as logo URLs.
BRAND_DOMAINS = {
    "Honda": "honda2wheelersindia.com", "TVS": "tvsmotor.com",
    "Suzuki": "suzukimotorcycle.co.in", "Yamaha": "yamaha-motor-india.com",
    "Hero": "heromotocorp.com", "Bajaj": "bajajauto.com",
    "Ather": "atherenergy.com", "Ola Electric": "olaelectric.com",
    "Vida": "vidaworld.com", "Vespa": "vespa.com", "Aprilia": "aprilia.com",
    "Royal Enfield": "royalenfield.com", "KTM": "ktm.com",
    "Kawasaki": "kawasaki.com", "Triumph": "triumphmotorcycles.com",
    "BMW Motorrad": "bmwmotorcycles.com", "Ducati": "ducati.com",
    "Jawa": "jawamotorcycles.com", "Yezdi": "yezdi.com",
    "Husqvarna": "husqvarna-motorcycles.com", "Harley-Davidson": "harley-davidson.com",
    "Indian Motorcycle": "indianmotorcycle.com", "Benelli": "benelli.com",
    "Moto Guzzi": "motoguzzi.com", "QJMotor": "qjmotor.com", "Keeway": "keeway.com",
}


def seed_india_bike_catalogue(apps, schema_editor):
    VehicleMake = apps.get_model("catalog", "VehicleMake")
    VehicleModel = apps.get_model("catalog", "VehicleModel")

    for make_order, (make_name, classes) in enumerate(BIKE_CATALOGUE.items(), start=1):
        make, _ = VehicleMake.objects.get_or_create(
            vehicle_type="bike",
            name=make_name,
            defaults={"sort_order": make_order, "is_active": True},
        )
        domain = BRAND_DOMAINS.get(make_name)
        if domain and not make.logo_url:
            make.logo_url = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
            make.save(update_fields=["logo_url"])
        for class_order, (vehicle_class, model_names) in enumerate(classes.items()):
            for model_order, model_name in enumerate(model_names, start=1):
                VehicleModel.objects.update_or_create(
                    make=make,
                    name=model_name,
                    defaults={
                        "vehicle_class": vehicle_class,
                        "sort_order": class_order * 100 + model_order,
                        "is_active": True,
                    },
                )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0021_seed_india_car_catalogue"),
    ]

    operations = [
        migrations.RunPython(seed_india_bike_catalogue, migrations.RunPython.noop),
    ]
