from django.db import migrations


# Commonly owned/current Indian-market passenger cars, plus widely seen older models.
# Model images are exact-name Commons photographs where a suitable source was found.
# Missing image URLs are intentionally left blank rather than showing another car as the wrong model.
CAR_MAKES = {
    "Maruti Suzuki": [
        ("Alto 800", "Hatchback"), ("Alto K10", "Hatchback"), ("S-Presso", "Hatchback"),
        ("Celerio", "Hatchback"), ("WagonR", "Hatchback"), ("Swift", "Hatchback"),
        ("Ignis", "Hatchback"), ("Baleno", "Hatchback"), ("Fronx", "Compact SUV"),
        ("Brezza", "Compact SUV"), ("Grand Vitara", "SUV – 5 Seater"),
        ("Jimny", "SUV – 5 Seater"), ("Ertiga", "MUV / MPV"), ("XL6", "MUV / MPV"),
        ("Dzire", "Sedan"), ("Ciaz", "Sedan"), ("Eeco", "MUV / MPV"),
        ("S-Cross", "SUV – 5 Seater"), ("Vitara Brezza", "Compact SUV"),
        ("Ritz", "Hatchback"), ("Celerio X", "Hatchback"), ("Kizashi", "Sedan"),
        ("Grand Vitara (Old)", "SUV – 5 Seater"), ("Omni", "MUV / MPV"),
        ("Esteem", "Sedan"), ("A-Star", "Hatchback"), ("800", "Hatchback"),
        ("e Vitara", "SUV – 5 Seater"),
    ],
    "Hyundai": [
        ("Santro", "Hatchback"), ("Eon", "Hatchback"), ("Grand i10", "Hatchback"),
        ("Grand i10 Nios", "Hatchback"), ("i10", "Hatchback"), ("i20", "Hatchback"),
        ("Elite i20", "Hatchback"), ("i20 Active", "Compact SUV"), ("Aura", "Sedan"),
        ("Xcent", "Sedan"), ("Verna", "Sedan"), ("Elantra", "Sedan"),
        ("Accent", "Sedan"), ("Exter", "Compact SUV"), ("Venue", "Compact SUV"),
        ("Creta", "SUV – 5 Seater"), ("Alcazar", "SUV – 7 Seater"),
        ("Tucson", "Luxury SUV"), ("Kona Electric", "SUV – 5 Seater"),
        ("Ioniq 5", "SUV – 5 Seater"), ("Santa Fe", "SUV – 7 Seater"),
    ],
    "Tata": [
        ("Nano", "Hatchback"), ("Indica", "Hatchback"), ("Indigo", "Sedan"),
        ("Bolt", "Hatchback"), ("Zest", "Sedan"), ("Tiago", "Hatchback"),
        ("Tiago EV", "Hatchback"), ("Tigor", "Sedan"), ("Tigor EV", "Sedan"),
        ("Altroz", "Hatchback"), ("Punch", "Compact SUV"), ("Punch EV", "Compact SUV"),
        ("Nexon", "Compact SUV"), ("Nexon EV", "Compact SUV"), ("Curvv", "SUV – 5 Seater"),
        ("Curvv EV", "SUV – 5 Seater"), ("Harrier", "SUV – 5 Seater"),
        ("Harrier EV", "SUV – 5 Seater"), ("Safari", "SUV – 7 Seater"),
        ("Sierra", "SUV – 5 Seater"), ("Hexa", "MUV / MPV"), ("Aria", "MUV / MPV"),
        ("Sumo", "MUV / MPV"), ("Sumo Gold", "MUV / MPV"), ("Venture", "MUV / MPV"),
    ],
    "Mahindra": [
        ("Bolero", "MUV / MPV"), ("Bolero Neo", "MUV / MPV"), ("Bolero Neo Plus", "MUV / MPV"),
        ("Scorpio", "SUV – 7 Seater"), ("Scorpio Classic", "SUV – 7 Seater"),
        ("Scorpio-N", "SUV – 7 Seater"), ("Thar", "SUV – 5 Seater"), ("Thar Roxx", "SUV – 5 Seater"),
        ("Thar 5-Door", "SUV – 5 Seater"), ("XUV300", "Compact SUV"), ("XUV 3XO", "Compact SUV"),
        ("XUV500", "SUV – 7 Seater"), ("XUV700", "SUV – 7 Seater"), ("XUV 7XO", "SUV – 7 Seater"),
        ("Marazzo", "MUV / MPV"), ("KUV100", "Compact SUV"), ("TUV300", "Compact SUV"),
        ("BE 6", "SUV – 5 Seater"), ("XEV 9e", "SUV – 5 Seater"), ("XEV 9S", "SUV – 7 Seater"),
        ("Alturas G4", "Luxury SUV"), ("Verito", "Sedan"), ("Quanto", "MUV / MPV"),
    ],
    "Toyota": [
        ("Etios Liva", "Hatchback"), ("Etios", "Sedan"), ("Glanza", "Hatchback"),
        ("Urban Cruiser Taisor", "Compact SUV"), ("Urban Cruiser", "Compact SUV"),
        ("Urban Cruiser Hyryder", "SUV – 5 Seater"), ("Innova", "MUV / MPV"),
        ("Innova Crysta", "MUV / MPV"), ("Innova Hycross", "MUV / MPV"),
        ("Fortuner", "Luxury SUV"), ("Fortuner Legender", "Luxury SUV"),
        ("Hilux", "SUV – 5 Seater"), ("Camry", "Sedan"), ("Corolla Altis", "Sedan"),
        ("Yaris", "Sedan"), ("Corolla", "Sedan"), ("Qualis", "MUV / MPV"),
        ("Land Cruiser 300", "Luxury SUV"), ("Vellfire", "MUV / MPV"),
    ],
    "Kia": [
        ("Sonet", "Compact SUV"), ("Seltos", "SUV – 5 Seater"), ("Carens", "MUV / MPV"),
        ("Carens Clavis", "MUV / MPV"), ("Carnival", "MUV / MPV"),
        ("EV6", "SUV – 5 Seater"), ("EV9", "Luxury SUV"), ("Syros", "Compact SUV"),
        ("Sonet (Old)", "Compact SUV"), ("Sportage", "SUV – 5 Seater"),
    ],
    "Honda": [
        ("Brio", "Hatchback"), ("Jazz", "Hatchback"), ("Amaze", "Sedan"),
        ("City", "Sedan"), ("City e:HEV", "Sedan"), ("Civic", "Sedan"),
        ("Accord", "Sedan"), ("WR-V", "Compact SUV"), ("BR-V", "MUV / MPV"),
        ("Mobilio", "MUV / MPV"), ("Elevate", "SUV – 5 Seater"), ("CR-V", "Luxury SUV"),
    ],
    "Renault": [
        ("Kwid", "Hatchback"), ("Triber", "MUV / MPV"), ("Kiger", "Compact SUV"),
        ("Duster", "SUV – 5 Seater"), ("Lodgy", "MUV / MPV"), ("Captur", "SUV – 5 Seater"),
        ("Fluence", "Sedan"), ("Pulse", "Hatchback"), ("Scala", "Sedan"),
    ],
    "Nissan": [
        ("Magnite", "Compact SUV"), ("Kicks", "SUV – 5 Seater"), ("Terrano", "SUV – 5 Seater"),
        ("Micra", "Hatchback"), ("Sunny", "Sedan"), ("Evalia", "MUV / MPV"),
        ("X-Trail", "SUV – 5 Seater"), ("Gravite", "MUV / MPV"),
    ],
    "MG": [
        ("Comet EV", "Hatchback"), ("Astor", "SUV – 5 Seater"), ("Hector", "SUV – 5 Seater"),
        ("Hector Plus", "SUV – 7 Seater"), ("Gloster", "Luxury SUV"),
        ("ZS EV", "SUV – 5 Seater"), ("Windsor EV", "SUV – 5 Seater"),
        ("Cyberster", "Luxury Car"), ("M9", "MUV / MPV"), ("Majestor", "Luxury SUV"),
    ],
    "Skoda": [
        ("Kylaq", "Compact SUV"), ("Kushaq", "SUV – 5 Seater"), ("Slavia", "Sedan"),
        ("Kodiaq", "Luxury SUV"), ("Superb", "Sedan"), ("Octavia", "Sedan"),
        ("Rapid", "Sedan"), ("Fabia", "Hatchback"), ("Yeti", "SUV – 5 Seater"),
        ("Laura", "Sedan"), ("Karoq", "SUV – 5 Seater"),
    ],
    "Volkswagen": [
        ("Polo", "Hatchback"), ("Vento", "Sedan"), ("Virtus", "Sedan"),
        ("Taigun", "SUV – 5 Seater"), ("Tiguan", "Luxury SUV"), ("T-Roc", "SUV – 5 Seater"),
        ("Jetta", "Sedan"), ("Passat", "Sedan"), ("Ameo", "Sedan"),
    ],
    "BMW": [
        ("2 Series Gran Coupe", "Sedan"), ("3 Series", "Sedan"), ("5 Series", "Sedan"),
        ("7 Series", "Luxury Car"), ("X1", "Compact SUV"), ("X3", "SUV – 5 Seater"),
        ("X5", "Luxury SUV"), ("X7", "Luxury SUV"), ("iX1", "SUV – 5 Seater"),
        ("iX", "Luxury SUV"), ("i4", "Sedan"), ("i5", "Luxury Car"),
        ("i7", "Luxury Car"), ("M340i", "Sedan"),
    ],
    "Audi": [
        ("A3", "Sedan"), ("A4", "Sedan"), ("A6", "Sedan"), ("A8 L", "Luxury Car"),
        ("Q3", "Compact SUV"), ("Q3 Sportback", "Compact SUV"), ("Q5", "SUV – 5 Seater"),
        ("Q7", "Luxury SUV"), ("Q8", "Luxury SUV"), ("Q8 e-tron", "Luxury SUV"),
        ("e-tron GT", "Luxury Car"), ("S5 Sportback", "Luxury Car"), ("RS Q8", "Luxury SUV"),
    ],
    "Mercedes-Benz": [
        ("A-Class Limousine", "Sedan"), ("C-Class", "Sedan"), ("E-Class", "Luxury Car"),
        ("S-Class", "Luxury Car"), ("CLA", "Sedan"), ("GLA", "Compact SUV"),
        ("GLB", "SUV – 7 Seater"), ("GLC", "SUV – 5 Seater"), ("GLE", "Luxury SUV"),
        ("GLS", "Luxury SUV"), ("EQA", "SUV – 5 Seater"), ("EQB", "SUV – 7 Seater"),
        ("EQE SUV", "Luxury SUV"), ("EQS", "Luxury Car"), ("G-Class", "Luxury SUV"),
    ],
    "Jeep": [
        ("Compass", "SUV – 5 Seater"), ("Meridian", "SUV – 7 Seater"),
        ("Wrangler", "Luxury SUV"), ("Grand Cherokee", "Luxury SUV"),
        ("Renegade", "Compact SUV"),
    ],
    "Citroen": [
        ("C3", "Hatchback"), ("eC3", "Hatchback"), ("C3 Aircross", "SUV – 7 Seater"),
        ("Basalt", "SUV – 5 Seater"), ("C5 Aircross", "Luxury SUV"),
    ],
    "BYD": [
        ("Atto 3", "SUV – 5 Seater"), ("e6", "MUV / MPV"), ("Seal", "Sedan"),
        ("Sealion 7", "SUV – 5 Seater"), ("Sealion 6", "SUV – 5 Seater"),
    ],
    "Volvo": [
        ("XC40", "SUV – 5 Seater"), ("EX40", "SUV – 5 Seater"), ("XC60", "Luxury SUV"),
        ("XC90", "Luxury SUV"), ("S90", "Luxury Car"), ("C40 Recharge", "SUV – 5 Seater"),
        ("EC40", "SUV – 5 Seater"),
    ],
    "Isuzu": [
        ("D-Max V-Cross", "SUV – 5 Seater"), ("MU-X", "SUV – 7 Seater"),
        ("D-Max S-CAB", "MUV / MPV"),
    ],
    "Force Motors": [("Gurkha", "SUV – 5 Seater"), ("Trax Cruiser", "MUV / MPV")],
    "MINI": [("Cooper 3-Door", "Hatchback"), ("Cooper 5-Door", "Hatchback"), ("Countryman", "SUV – 5 Seater"), ("Convertible", "Luxury Car")],
}

MODEL_IMAGES = {
    "Maruti Suzuki|Swift": "Suzuki_Swift_(2024)_hybrid_DSC_7922.jpg",
    "Maruti Suzuki|Dzire": "Suzuki_Dzire_2024_ZXI%2B.jpg",
    "Maruti Suzuki|Brezza": "Maruti_Suzuki_Brezza_-_front.jpg",
    "Maruti Suzuki|Fronx": "2023_Suzuki_Fronx_1.2_Delta%2B_%28India%29_front_view.png",
    "Maruti Suzuki|Ertiga": "2022_Maruti_Suzuki_Ertiga_LXi.jpg",
    "Hyundai|Grand i10 Nios": "2021_Hyundai_Grand_i10_Nios_1.0AT_Standard_red_front_view_in_Brunei.jpg",
    "Hyundai|i20": "Hyundai_i20_front.JPG",
    "Hyundai|Venue": "2020_Hyundai_Venue_Ultimate_2019-12-13_2.jpg",
    "Hyundai|Creta": "2024_Hyundai_Creta_1.5_MPi_SX%28O%29_%28India%29_front_view.png",
    "Tata|Tiago": "Tata_tiago.jpg",
    "Tata|Punch": "2021_Tata_Punch_Creative_%28India%29_front_view_01.png",
    "Tata|Nexon": "2023_Tata_Nexon_XZA%2B_front_view.jpg",
    "Mahindra|XUV 3XO": "2025_Mahindra_XUV_3XO_AX7L_front.jpg",
    "Mahindra|XUV700": "2021_Mahindra_XUV700_2.2_AX7_%28India%29_front_view.png",
    "Mahindra|Thar Roxx": "Mahindra_Thar_ROXX_on_dirt.jpg",
    "Mahindra|Scorpio Classic": "Mahindra_Scorpio_2014.JPG",
    "Toyota|Innova Crysta": "Toyota_Innova_Crysta.jpg",
    "Toyota|Fortuner": "Toyota_Fortuner_4x2_G_2021.jpg",
    "Kia|Sonet": "Kia_Sonet_front_view_%28India%29_01.png",
    "Kia|Seltos": "Kia_Seltos_IMG_9152.jpg",
    "Kia|Carens": "2022_Kia_Carens_1.4_%28India%29_front_view_01.jpg",
    "Kia|Syros": "2025_Kia_Syros_1.5_HTX%2B_%28O%29_%28India%29_front_view_01.jpg",
    "Hyundai|Alcazar": "2021_Hyundai_Alcazar_1.5_Prestige_%28India%29_front_view.png",
    "Honda|City": "2022_Honda_City_ZX_i-VTEC_%28India%29_front_view_%28cropped%29.jpg",
    "Honda|Elevate": "2023_Honda_Elevate_VX_%28India%29_front_view.jpg",
    "Renault|Kwid": "Renault_Kwid.jpg",
}

MAKE_LOGOS = {
    "BMW": "https://commons.wikimedia.org/wiki/Special:FilePath/BMW.svg",
    "Audi": "https://commons.wikimedia.org/wiki/Special:FilePath/Audi_logo.svg",
    "Mercedes-Benz": "https://commons.wikimedia.org/wiki/Special:FilePath/Mercedes-Benz_logo.svg",
    "Maruti Suzuki": "https://commons.wikimedia.org/wiki/Special:FilePath/Maruti_Suzuki_logo.svg",
    "Hyundai": "https://commons.wikimedia.org/wiki/Special:FilePath/Hyundai_logo.svg",
    "Tata": "https://commons.wikimedia.org/wiki/Special:FilePath/Tata_Motors_Logo.svg",
    "Honda": "https://commons.wikimedia.org/wiki/Special:FilePath/Honda_Logo.svg",
    "Toyota": "https://commons.wikimedia.org/wiki/Special:FilePath/Toyota_Logo.svg",
    "Kia": "https://commons.wikimedia.org/wiki/Special:FilePath/KIA_logo.svg",
    "Mahindra": "https://commons.wikimedia.org/wiki/Special:FilePath/Mahindra_Automotive_new_logo.png",
    "Volkswagen": "https://commons.wikimedia.org/wiki/Special:FilePath/Volkswagen_-_Logo.svg",
    "MG": "https://commons.wikimedia.org/wiki/Special:FilePath/MG_Motor_2021_logo.svg",
    "Renault": "https://commons.wikimedia.org/wiki/Special:FilePath/Renault_Logo.svg",
    "Nissan": "https://commons.wikimedia.org/wiki/Special:FilePath/Nissan_2020_logo.svg",
    "Skoda": "https://commons.wikimedia.org/wiki/Special:FilePath/Skoda_Logo.png",
}


def seed_india_car_catalogue(apps, schema_editor):
    VehicleMake = apps.get_model("catalog", "VehicleMake")
    VehicleModel = apps.get_model("catalog", "VehicleModel")
    for make_order, (make_name, models) in enumerate(CAR_MAKES.items(), start=1):
        make, _ = VehicleMake.objects.get_or_create(
            vehicle_type="car", name=make_name,
            defaults={"sort_order": make_order, "is_active": True},
        )
        logo_url = MAKE_LOGOS.get(make_name, "")
        if logo_url and not make.logo_url:
            make.logo_url = logo_url
            make.save(update_fields=["logo_url"])
        for model_order, (model_name, vehicle_class) in enumerate(models, start=1):
            image_file = MODEL_IMAGES.get(f"{make_name}|{model_name}", "")
            image_url = (
                f"https://commons.wikimedia.org/wiki/Special:FilePath/{image_file}?width=720"
                if image_file else ""
            )
            VehicleModel.objects.update_or_create(
                make=make, name=model_name,
                defaults={
                    "vehicle_class": vehicle_class,
                    "sort_order": model_order,
                    "is_active": True,
                    "image_url": image_url,
                },
            )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0020_vehicle_catalogue_remote_images"),
    ]

    operations = [
        migrations.RunPython(seed_india_car_catalogue, migrations.RunPython.noop),
    ]
