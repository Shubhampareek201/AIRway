from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from apps.catalog.models import (
    AddOn, Category, FormField, Service, ServiceVariant,
)


VEHICLES = [
    "Hatchback", "Sedan", "Compact SUV", "SUV – 5 Seater",
    "SUV – 7 Seater", "MUV / MPV", "Luxury Car",
    "Luxury SUV",
]


class CatalogueBuilder:
    def __init__(self, stdout):
        self.stdout = stdout
        self.counts = {"categories": 0, "services": 0, "packages": 0, "addons": 0, "questions": 0}

    def category(self, title, parent=None):
        slug = slugify(title)
        obj, created = Category.objects.get_or_create(
            slug=slug,
            defaults={"title": title, "parent": parent, "is_active": True},
        )
        if created:
            self.counts["categories"] += 1
        elif obj.parent_id != (parent.id if parent else None):
            raise ValueError(
                f"Category slug '{slug}' already exists under a different parent. "
                "Resolve it in Admin before seeding."
            )
        return obj

    def field(self, service, key, label, field_type="text", options=None, required=False):
        obj, created = FormField.objects.get_or_create(
            service=service,
            key=key,
            defaults={
                "label": label,
                "field_type": field_type,
                "options": options or [],
                "is_required": required,
                "is_active": True,
            },
        )
        if created:
            self.counts["questions"] += 1
        return obj

    def package(self, service, title, description, tasks=None, duration=60, attributes=None):
        obj, created = ServiceVariant.objects.get_or_create(
            service=service,
            title=title,
            defaults={
                "description": description,
                "included_tasks": tasks or [],
                "duration_minutes": duration,
                "attributes": attributes or {},
                "mrp": Decimal("0.00"),
                "price": Decimal("0.00"),
                "is_active": True,
            },
        )
        if created:
            self.counts["packages"] += 1
        return obj

    def addon(self, service, title, description="Optional extra work"):
        obj, created = AddOn.objects.get_or_create(
            service=service,
            title=title,
            defaults={
                "description": description,
                "mrp": Decimal("0.00"),
                "price": Decimal("0.00"),
                "is_active": True,
            },
        )
        if created:
            self.counts["addons"] += 1
        return obj

    def service(
        self, category, title, description, *, audience="all",
        booking_mode="scheduled", pricing_type="fixed", duration=60,
        popular=False, fields=None, packages=None, addons=None,
    ):
        obj, created = Service.objects.get_or_create(
            category=category,
            title=title,
            defaults={
                "description": description,
                "audience": audience,
                "booking_mode": booking_mode,
                "pricing_type": pricing_type,
                "duration_minutes": duration,
                "visit_fee": Decimal("0.00"),
                "is_popular": popular,
                "is_active": True,
            },
        )
        if created:
            self.counts["services"] += 1
        for item in fields or []:
            self.field(obj, **item)
        for item in packages or []:
            self.package(obj, **item)
        for item in addons or []:
            self.addon(obj, **(item if isinstance(item, dict) else {"title": item}))
        return obj


class Command(BaseCommand):
    help = (
        "Create AIRway's launch catalogue from the approved four-category master list. "
        "Safe to rerun: existing records and admin-configured values are not overwritten."
    )

    def handle(self, *args, **options):
        b = CatalogueBuilder(self.stdout)
        self._car_wash(b)
        self._beauty(b)
        self._electrical(b)
        self._home_cleaning(b)
        self.stdout.write(self.style.SUCCESS(
            "AIRway catalogue seed complete: " +
            ", ".join(f"{key} +{value}" for key, value in b.counts.items())
        ))
        self.stdout.write(
            "All seeded prices are intentionally unconfigured (₹0 in Admin); "
            "configure real rates before publishing paid bookings."
        )

    def _car_wash(self, b):
        root = b.category("Car Wash")
        groups = {
            name: b.category(name, root) for name in [
                "Exterior Car Cleaning", "Interior Car Cleaning",
                "Complete Car Cleaning", "Car Detailing & Paint Protection",
                "Monthly Car Wash Plans",
            ]
        }
        vehicle_field = {
            "key": "vehicle_type", "label": "Vehicle type", "field_type": "select",
            "options": VEHICLES, "required": True,
        }
        for group_name, service_title, packages, addons in [
            ("Exterior Car Cleaning", "Exterior Car Wash", [
                ("Basic Exterior Wash", "Water wash and routine exterior cleaning.",
                 ["Water wash", "Body shampoo", "Dust and mud removal", "Exterior glass cleaning"], 45),
                ("Deep Exterior Wash", "Foam and detailed exterior cleaning.",
                 ["Foam wash", "Pressure wash", "Detailed body cleaning", "Wheel and rim cleaning", "Tyre cleaning"], 60),
                ("Premium Exterior Wash", "Deep exterior wash with finishing treatments.",
                 ["Deep exterior wash", "Tyre polishing", "Detailed rim cleaning", "Exterior finishing", "Protective wax where included"], 75),
            ], [
                "Tyre Polish", "Underbody Cleaning", "Engine Bay Cleaning",
                "Hard Water Stain Removal", "Bird Dropping Removal",
            ]),
            ("Interior Car Cleaning", "Interior Car Cleaning", [
                ("Basic Interior Cleaning", "Routine interior cleaning.",
                 ["Interior vacuuming", "Dashboard dusting", "Door panel cleaning", "Floor mats", "Interior glass"], 45),
                ("Deep Interior Cleaning", "Detailed interior cleaning.",
                 ["Deep vacuuming", "Seat cleaning", "Carpet cleaning", "Dashboard detailing", "Boot cleaning", "Detailed interior dust removal"], 90),
                ("Premium Interior Cleaning", "Deep interior treatment and finishing.",
                 ["Deep interior cleaning", "Fabric or leather treatment as applicable", "Detailed finishing", "Interior sanitization"], 120),
            ], [
                "Seat Shampoo", "Leather Conditioning", "AC Vent Cleaning",
                "Roof Lining Cleaning", "Odour Removal", "Stain Removal",
            ]),
            ("Complete Car Cleaning", "Complete Car Cleaning", [
                ("Basic Complete Wash", "Basic exterior wash combined with basic interior cleaning.",
                 ["Basic Exterior Wash", "Basic Interior Cleaning"], 90),
                ("Deep Complete Wash", "Deep exterior wash combined with deep interior cleaning.",
                 ["Deep Exterior Wash", "Deep Interior Cleaning"], 150),
                ("Premium Complete Wash", "Premium exterior wash combined with premium interior cleaning.",
                 ["Premium Exterior Wash", "Premium Interior Cleaning"], 180),
            ], []),
        ]:
            service = b.service(
                groups[group_name], service_title,
                f"{service_title} for the selected vehicle. Choose a package and review its included work.",
                duration=60, popular=(group_name == "Exterior Car Cleaning"),
                fields=[vehicle_field],
            )
            for package_title, description, tasks, duration in packages:
                for vehicle in VEHICLES:
                    b.package(
                        service, f"{package_title} — {vehicle}",
                        description, tasks, duration,
                        attributes={"vehicle_type": vehicle},
                    )
            for addon in addons:
                b.addon(service, addon)

        detail_options = [
            "Rubbing & Polishing", "Paint Correction", "Wax Treatment",
            "Ceramic Coating", "Graphene Coating", "Headlight Restoration",
            "Scratch Reduction", "Engine Bay Detailing",
        ]
        for treatment in detail_options:
            b.service(
                groups["Car Detailing & Paint Protection"], treatment,
                "Specialist vehicle treatment. Final scope and price are confirmed after inspection.",
                booking_mode="inspection", pricing_type="quote", duration=90,
                fields=[
                    vehicle_field,
                    {"key": "vehicle_condition", "label": "Vehicle condition", "field_type": "select",
                     "options": ["Good", "Minor wear", "Heavy dirt or damage", "Not sure"], "required": True},
                    {"key": "paint_condition", "label": "Paint condition", "field_type": "select",
                     "options": ["Good", "Faded", "Scratched", "Stained", "Not sure"], "required": False},
                    {"key": "vehicle_photos", "label": "Upload vehicle photos", "field_type": "photo", "required": False},
                    {"key": "treatment_notes", "label": "Tell us what you need", "field_type": "textarea", "required": False},
                ],
            )

        monthly = b.service(
            groups["Monthly Car Wash Plans"], "Monthly Car Wash Plan",
            "Choose a recurring wash frequency. The team will confirm the plan, vehicle count and service schedule.",
            booking_mode="inspection", pricing_type="quote", duration=30,
            fields=[
                vehicle_field,
                {"key": "vehicle_quantity", "label": "Number of vehicles", "field_type": "number", "required": True},
                {"key": "subscription_duration", "label": "Plan duration", "field_type": "select",
                 "options": ["15 days", "1 month", "3 months", "6 months"], "required": True},
            ],
        )
        for title in ["Daily Wash Plan", "Alternate Day Wash Plan", "Weekly Wash Plan", "15-Day Plan", "Monthly Wash Plan"]:
            b.package(monthly, title, "Recurring wash frequency; final schedule and quote confirmed by AIRway.", [], 30)

    def _beauty(self, b):
        root = b.category("Beauty")
        groups = {name: b.category(name, root) for name in [
            "Hair Services", "Facial & Skin Care", "Threading", "Waxing",
            "Manicure & Pedicure", "Makeup & Occasion Styling", "Grooming & Massage",
        ]}
        def pkg(names, description="Choose the service level and confirm the exact inclusions with the provider."):
            return [{"title": n, "description": description, "tasks": [], "duration": 60} for n in names]

        hair = groups["Hair Services"]
        hair_services = [
            ("Men's Haircut", "men", ["Regular Haircut", "Premium Haircut"]),
            ("Men's Hair Styling", "men", ["Simple Styling", "Special Occasion Styling"]),
            ("Men's Hair Wash", "all", ["Basic Hair Wash", "Hair Wash + Blow Dry"]),
            ("Men's Haircut + Hair Wash", "men", []),
            ("Men's Hair Colour", "men", ["Root Touch-up", "Global Colour"]),
            ("Grey Hair Coverage", "men", ["Root Coverage", "Full Coverage"]),
            ("Men's Hair Spa", "men", ["Basic Hair Spa", "Deep Hair Spa", "Premium Hair Spa"]),
            ("Head Massage", "all", []),
            ("Women's Haircut", "women", ["Regular Haircut", "Premium Haircut"]),
            ("Hair Trimming", "women", []), ("Women's Hair Wash", "women", ["Basic Hair Wash", "Hair Wash + Blow Dry"]),
            ("Blow Dry", "women", []), ("Women's Hair Styling", "women", ["Simple Styling", "Party Styling", "Special Occasion Styling"]),
            ("Hair Curling", "women", []), ("Hair Straightening", "women", []),
            ("Hair Smoothening", "women", []), ("Keratin Treatment", "women", []),
            ("Hair Rebonding", "women", []), ("Women's Hair Spa", "women", ["Basic Hair Spa", "Deep Hair Spa", "Premium Hair Spa"]),
            ("Global Hair Colour", "women", []), ("Root Touch-up", "women", []), ("Hair Highlights", "women", []),
        ]
        for title, audience, packages in hair_services:
            b.service(hair, title, f"{title} at home by an appropriately skilled beauty professional.",
                      audience=audience, duration=60, packages=pkg(packages) if packages else [])

        skin = groups["Facial & Skin Care"]
        for title in ["Face Cleanup", "Fruit Facial", "Gold Facial", "Diamond Facial", "Pearl Facial",
                      "Charcoal Facial", "Hydrating Facial", "Anti-Tan Facial", "Brightening Facial",
                      "Bridal Facial", "Face Bleaching"]:
            b.service(skin, title, f"{title}; products, steps and duration are confirmed in the selected package.",
                      audience="all", duration=60,
                      packages=pkg(["Basic Facial", "Deep Cleansing Facial", "Premium Facial"]),
                      fields=[{"key": "skin_notes", "label": "Skin type or sensitivity (optional)", "field_type": "textarea", "required": False}])

        threading = groups["Threading"]
        for title in ["Eyebrow Threading", "Upper Lip Threading", "Lower Lip Threading", "Chin Threading",
                      "Forehead Threading", "Side Locks Threading", "Full Face Threading"]:
            b.service(threading, title, f"{title} with selected area and combination options.",
                      audience="women", duration=15)
        b.service(threading, "Threading Combination", "Select the areas required for a combined threading service.",
                  audience="women", duration=30,
                  fields=[{"key": "threading_areas", "label": "Select areas", "field_type": "select",
                           "options": ["Eyebrow", "Upper Lip", "Lower Lip", "Chin", "Forehead", "Side Locks", "Full Face"], "required": True}])

        waxing = groups["Waxing"]
        for area in ["Half Arms", "Full Arms", "Half Legs", "Full Legs", "Underarms", "Full Face",
                     "Bikini Line", "Bikini Wax", "Brazilian Wax", "Full Body Wax", "Chest Wax", "Back Wax"]:
            b.service(waxing, area, f"{area} waxing. Available wax type depends on provider capability and hygiene requirements.",
                      audience="women" if area not in ["Chest Wax", "Back Wax"] else "all",
                      duration=45, packages=pkg(["Regular Wax", "Rica Wax", "Premium Wax"]))

        nails = groups["Manicure & Pedicure"]
        for title in ["Manicure", "Spa Manicure", "Pedicure", "Spa Pedicure", "Gel Polish",
                      "Nail Art", "Nail Extensions", "Nail Removal"]:
            b.service(nails, title, f"{title} with products and finish confirmed before booking.",
                      audience="all", duration=60)

        makeup = groups["Makeup & Occasion Styling"]
        for title in ["Party Makeup", "Light Makeup", "Engagement Makeup", "Bridal Makeup", "HD Makeup",
                      "Hairstyling", "Bridal Hairstyle", "Party Hairstyle", "Saree Draping"]:
            b.service(makeup, title, f"{title} for events and occasions. Share reference photos for accurate preparation.",
                      audience="women", booking_mode="inspection" if title == "Bridal Makeup" else "scheduled",
                      pricing_type="quote" if title == "Bridal Makeup" else "fixed", duration=90,
                      packages=pkg(["Basic Party Package", "Premium Party Package"] if title in ["Party Makeup", "Light Makeup"]
                                    else ["Engagement Package", "Bridal Package"] if title in ["Engagement Makeup", "Bridal Makeup"]
                                    else []),
                      fields=[
                          {"key": "occasion", "label": "Occasion", "field_type": "text", "required": title in ["Party Makeup", "Engagement Makeup", "Bridal Makeup"]},
                          {"key": "event_date", "label": "Event date", "field_type": "date", "required": title in ["Engagement Makeup", "Bridal Makeup"]},
                          {"key": "people_count", "label": "Number of people", "field_type": "number", "required": False},
                          {"key": "makeup_style", "label": "Preferred style", "field_type": "select",
                           "options": ["Natural", "Soft Glam", "Traditional", "HD", "Not sure"], "required": False},
                          {"key": "reference_photos", "label": "Reference photos", "field_type": "photo", "required": False},
                      ])

        grooming = groups["Grooming & Massage"]
        for title in ["Beard Trim", "Beard Styling", "Clean Shave"]:
            b.service(grooming, title, f"{title} by a trained grooming professional.", audience="men", duration=30)
        for title in ["Hair Oil Massage", "Foot Massage", "Hand Massage", "Back Massage", "Full Body Spa"]:
            b.service(grooming, title, f"{title}; subject to appropriately trained staff and service availability.",
                      audience="all", duration=60,
                      booking_mode="inspection" if title == "Full Body Spa" else "scheduled",
                      pricing_type="quote" if title == "Full Body Spa" else "fixed")

    def _electrical(self, b):
        root = b.category("Electrical")
        groups = {name: b.category(name, root) for name in [
            "Fan Services", "Lighting Services", "Switch & Socket Services",
            "Wiring & Electrical Repairs", "Inverter & UPS",
            "Geyser & Electrical Connections", "Electrical Inspection & Setup",
        ]}
        common_fields = [
            {"key": "work_type", "label": "Work type", "field_type": "select",
             "options": ["Installation", "Repair", "Replacement", "Inspection"], "required": True},
            {"key": "quantity", "label": "Number of items", "field_type": "number", "required": True},
            {"key": "problem", "label": "Problem", "field_type": "select",
             "options": ["Not working", "Sparking", "Tripping", "Making noise", "Loose connection", "Other"], "required": False},
            {"key": "property_type", "label": "Property", "field_type": "select",
             "options": ["Home", "Shop", "Office"], "required": True},
            {"key": "material", "label": "Material", "field_type": "select",
             "options": ["Customer-provided", "Worker-supplied", "Need advice"], "required": True},
            {"key": "problem_photos", "label": "Upload problem photos", "field_type": "photo", "required": False},
            {"key": "problem_description", "label": "Explain the issue", "field_type": "textarea", "required": False},
        ]
        def electrical_service(group, title, *, quote=False, duration=60):
            return b.service(
                groups[group], title,
                f"{title}. Select the work type, quantity and issue details. Material charges are confirmed before work.",
                booking_mode="inspection" if quote else "scheduled",
                pricing_type="quote" if quote else "fixed",
                duration=duration,
                fields=common_fields,
            )

        for item in ["Ceiling Fan", "Wall Fan", "Exhaust Fan", "Decorative Fan"]:
            electrical_service("Fan Services", item)
        for item in ["Bulb", "LED", "Tube Light", "Panel Light", "Ceiling Light", "Wall Light",
                     "Chandelier", "Decorative Lights", "Outdoor Lights", "Strip Lights"]:
            electrical_service("Lighting Services", item)
        for item in ["Switch", "Socket", "Switchboard", "Plug Point", "USB Socket", "Doorbell",
                     "Loose Connection", "Burnt Socket"]:
            electrical_service("Switch & Socket Services", item, quote=item in ["Loose Connection", "Burnt Socket"])
        for item in ["New Wiring", "Old Wiring Replacement", "Wiring Repair", "Short Circuit Diagnosis",
                     "Power Failure Diagnosis", "MCB Installation", "MCB Tripping Repair", "Fuse Replacement",
                     "Earthing Work", "RCCB / ELCB Installation", "Voltage Fluctuation Diagnosis"]:
            electrical_service("Wiring & Electrical Repairs", item,
                               quote=item in ["New Wiring", "Old Wiring Replacement", "Wiring Repair",
                                              "Short Circuit Diagnosis", "Power Failure Diagnosis",
                                              "Earthing Work", "Voltage Fluctuation Diagnosis"])
        for item in ["Inverter Installation", "Inverter Repair", "Inverter Wiring",
                     "Battery Installation", "Battery Replacement", "UPS Installation",
                     "UPS Repair", "Charging Problem Diagnosis"]:
            electrical_service("Inverter & UPS", item, quote=item in ["Inverter Repair", "UPS Repair", "Charging Problem Diagnosis"])
        for item in ["Geyser Installation", "Geyser Electrical Connection", "Geyser Switch Replacement",
                     "Geyser Power Problem", "Water Pump Electrical Connection", "Motor Wiring",
                     "Motor Starter Repair"]:
            electrical_service("Geyser & Electrical Connections", item, quote=item in ["Geyser Power Problem", "Motor Wiring", "Motor Starter Repair"])
        for item in ["Full Home Electrical Inspection", "Electrical Safety Check", "New Room Electrical Setup",
                     "Additional Power Point", "Decorative Electrical Setup", "Smart Switch Installation",
                     "Smart Light Installation"]:
            electrical_service("Electrical Inspection & Setup", item, quote=item in ["Full Home Electrical Inspection", "Electrical Safety Check", "New Room Electrical Setup", "Decorative Electrical Setup"])

    def _home_cleaning(self, b):
        root = b.category("Home Cleaning")
        groups = {name: b.category(name, root) for name in [
            "Kitchen Cleaning", "Full Home Cleaning", "Bathroom Cleaning", "Garden Cleaning",
            "Bedroom Cleaning", "Living Room & Dining Room", "Sofa & Upholstery Cleaning",
            "Mattress Cleaning", "Carpet & Rug Cleaning", "Balcony & Terrace Cleaning",
            "Window & Glass Cleaning", "Floor Cleaning",
        ]}
        packages = {
            "Kitchen Cleaning": [
                ("Basic Kitchen Cleaning", "Routine kitchen surface cleaning.",
                 ["Countertop cleaning", "Sink cleaning", "External cabinet cleaning", "Visible dust removal", "Floor cleaning"], 90),
                ("Deep Kitchen Cleaning", "Basic work plus grease, tile and cabinet detailing.",
                 ["Countertop and sink cleaning", "Grease removal", "Tile cleaning", "Cabinet exterior and interior cleaning", "Chimney exterior cleaning", "Detailed sink cleaning"], 150),
                ("Premium Kitchen Cleaning", "Deep kitchen cleaning with appliance exterior and finishing work.",
                 ["Deep kitchen cleaning", "Additional appliance exterior cleaning", "Detailed finishing", "Selected hard-stain treatment"], 180),
            ],
            "Full Home Cleaning": [
                ("Basic Full Home Cleaning", "General cleaning for commonly used home surfaces.",
                 ["General dusting", "Sweeping", "Mopping", "Visible surface cleaning", "Basic bathroom cleaning", "Basic kitchen cleaning"], 180),
                ("Deep Full Home Cleaning", "Detailed room-by-room cleaning.",
                 ["Basic full home tasks", "Detailed room cleaning", "Fans", "Doors", "Furniture", "Corners", "Kitchen deep cleaning", "Bathroom deep cleaning"], 300),
                ("Premium Full Home Cleaning", "Deep cleaning with additional surface treatment and finishing.",
                 ["Deep full home cleaning", "Detailed surface treatment", "Selected glass and hard-to-reach areas", "Extra finishing"], 360),
            ],
            "Bathroom Cleaning": [
                ("Basic Bathroom Cleaning", "Routine bathroom cleaning.",
                 ["Toilet", "Washbasin", "Floor", "Visible surface cleaning"], 45),
                ("Deep Bathroom Cleaning", "Detailed tile, shower and fitting cleaning.",
                 ["Basic bathroom tasks", "Tiles", "Shower area", "Fittings", "Hard-water stains", "Grout cleaning"], 75),
                ("Premium Bathroom Cleaning", "Deep cleaning with detailed finishing.",
                 ["Deep bathroom cleaning", "Detailed fittings", "Glass", "Corners", "Additional stain treatment"], 90),
            ],
            "Garden Cleaning": [
                ("Basic Garden Cleaning", "Basic outdoor garden cleanup.",
                 ["Dry leaf collection", "Sweeping", "Visible waste removal", "Basic cleanup"], 60),
                ("Deep Garden Cleaning", "Detailed garden cleanup.",
                 ["Basic garden tasks", "Weed removal", "Plant area cleanup", "Detailed corner cleaning"], 120),
                ("Garden Maintenance", "Routine plant and garden maintenance.",
                 ["Plant trimming", "Watering", "Pruning", "Routine garden care"], 90),
            ],
            "Bedroom Cleaning": [
                ("Basic Bedroom Cleaning", "Routine bedroom cleaning.",
                 ["Dusting", "Sweeping", "Mopping", "Visible furniture cleaning"], 60),
                ("Deep Bedroom Cleaning", "Detailed bedroom cleaning.",
                 ["Basic bedroom tasks", "Bed area", "Furniture", "Wardrobe exterior", "Fans", "Corners"], 90),
                ("Premium Bedroom Cleaning", "Deep cleaning with additional surface finishing.",
                 ["Deep bedroom cleaning", "Selected interior surfaces", "Detailed finishing", "Additional dust removal"], 120),
            ],
            "Living Room & Dining Room": [
                ("Basic Living & Dining Cleaning", "Routine living and dining area cleaning.",
                 ["Dusting", "Floor cleaning", "Table cleaning", "Visible furniture cleaning"], 60),
                ("Deep Living & Dining Cleaning", "Detailed furniture and room cleaning.",
                 ["Basic living and dining tasks", "Sofa exterior", "TV unit", "Doors", "Fans", "Corners"], 90),
                ("Premium Living & Dining Cleaning", "Deep cleaning with selected glass and furniture finishing.",
                 ["Deep living and dining cleaning", "Detailed furniture surfaces", "Selected glass surfaces", "Finishing"], 120),
            ],
            "Sofa & Upholstery Cleaning": [
                ("Basic Sofa Cleaning", "Vacuuming and surface dust removal.",
                 ["Vacuuming", "Surface dust removal", "Visible dirt removal"], 45),
                ("Deep Sofa Cleaning", "Fabric cleaning with suitable shampoo and extraction.",
                 ["Deep vacuuming", "Fabric cleaning", "Shampoo treatment", "Extraction where suitable"], 90),
                ("Premium Sofa Cleaning", "Deep cleaning with suitable stain treatment and finishing.",
                 ["Deep sofa cleaning", "Suitable stain treatment", "Finishing"], 120),
            ],
            "Mattress Cleaning": [
                ("Basic Mattress Cleaning", "Surface dust removal.",
                 ["Vacuuming", "Surface dust removal"], 45),
                ("Deep Mattress Cleaning", "Deep vacuuming and suitable stain treatment.",
                 ["Deep vacuuming", "Suitable stain treatment"], 75),
                ("Premium Mattress Cleaning", "Deep cleaning with additional sanitization where suitable.",
                 ["Deep mattress cleaning", "Additional sanitization treatment where suitable"], 90),
            ],
            "Carpet & Rug Cleaning": [
                ("Basic Carpet Cleaning", "Routine carpet cleaning.",
                 ["Surface vacuuming", "Dust and loose dirt removal"], 45),
                ("Deep Carpet Cleaning", "Detailed carpet cleaning.",
                 ["Deep vacuuming", "Suitable carpet wash or extraction"], 90),
                ("Premium Carpet Cleaning", "Deep carpet cleaning with finishing.",
                 ["Deep carpet cleaning", "Suitable stain treatment", "Finishing"], 120),
            ],
            "Balcony & Terrace Cleaning": [
                ("Basic Balcony Cleaning", "Routine balcony cleaning.",
                 ["Sweeping", "Visible dust removal", "Floor cleaning"], 45),
                ("Deep Balcony Cleaning", "Detailed balcony cleaning.",
                 ["Basic balcony tasks", "Corners", "Railings", "Drain area cleaning"], 75),
                ("Premium Balcony Cleaning", "Deep balcony and outdoor finishing.",
                 ["Deep balcony cleaning", "Outdoor floor cleaning", "Detailed finishing"], 90),
            ],
            "Window & Glass Cleaning": [
                ("Basic Window Cleaning", "Routine window and glass cleaning.",
                 ["Accessible glass surface cleaning", "Frame dust removal"], 45),
                ("Deep Window Cleaning", "Detailed window and glass cleaning.",
                 ["Interior glass cleaning", "Glass door cleaning", "Accessible frame detailing"], 75),
            ],
            "Floor Cleaning": [
                ("Basic Floor Cleaning", "Routine floor cleaning.",
                 ["Sweeping", "Mopping", "Visible dirt removal"], 60),
                ("Deep Floor Scrubbing", "Detailed floor scrubbing.",
                 ["Deep floor scrubbing", "Tile cleaning", "Grout cleaning"], 120),
            ],
        }
        addons = {
            "Kitchen Cleaning": ["Chimney Cleaning", "Refrigerator Interior Cleaning", "Microwave Interior Cleaning", "Oven Cleaning", "Cabinet Interior Cleaning"],
            "Bathroom Cleaning": ["Bathtub Cleaning", "Exhaust Fan Cleaning", "Extra Bathroom", "Hard Water Stain Treatment"],
            "Garden Cleaning": ["Grass Cutting", "Hedge Trimming", "Plant Pruning", "Soil Replacement", "Plant Repotting", "Waste Disposal"],
            "Bedroom Cleaning": ["Wardrobe Interior", "Mattress Cleaning", "Curtain Cleaning", "Window Cleaning", "Fan Cleaning"],
            "Living Room & Dining Room": ["Sofa Cleaning", "Dining Chair Cleaning", "Window Cleaning", "Glass Cleaning"],
            "Carpet & Rug Cleaning": ["Stain Removal", "Odour Treatment"],
        }
        for group_name, package_list in packages.items():
            service = b.service(
                groups[group_name], group_name,
                f"{group_name} at home. Choose a suitable package, review included tasks and select optional extras.",
                duration=90, popular=group_name in ["Kitchen Cleaning", "Full Home Cleaning"],
                packages=[
                    {"title": title, "description": desc, "tasks": tasks, "duration": duration}
                    for title, desc, tasks, duration in package_list
                ],
                addons=addons.get(group_name, []),
            )
            if group_name == "Kitchen Cleaning":
                b.field(service, "kitchen_count", "Number of kitchens", "number", required=True)
                b.field(service, "kitchen_size", "Approximate kitchen size", "select",
                        ["Small", "Medium", "Large", "Not sure"], required=True)
                b.field(service, "kitchen_condition", "Current condition", "select",
                        ["Light cleaning", "Greasy", "Heavy stains", "Not sure"], required=True)
                b.field(service, "kitchen_photos", "Upload kitchen photos", "photo", required=False)
            elif group_name == "Sofa & Upholstery Cleaning":
                b.field(service, "sofa_type", "Sofa / upholstery type", "select",
                        ["1 Seater", "2 Seater", "3 Seater", "4 Seater", "L-Shaped Sofa", "U-Shaped Sofa", "Recliner", "Dining Chairs"], True)
                b.field(service, "sofa_quantity", "Number of items", "number", required=True)
                b.field(service, "sofa_photos", "Upload sofa photos", "photo", required=False)
            elif group_name == "Mattress Cleaning":
                b.field(service, "mattress_size", "Mattress size", "select",
                        ["Single", "Double", "Queen", "King"], required=True)
                b.field(service, "mattress_quantity", "Number of mattresses", "number", required=True)
            elif group_name == "Carpet & Rug Cleaning":
                b.field(service, "carpet_size", "Carpet size", "select",
                        ["Small", "Medium", "Large", "Custom Size"], required=True)
                b.field(service, "carpet_photos", "Upload carpet photos", "photo", required=False)
            elif group_name == "Full Home Cleaning":
                b.field(service, "bedroom_count", "Number of bedrooms", "number", required=True)
                b.field(service, "bathroom_count", "Number of bathrooms", "number", required=True)
                b.field(service, "property_size", "Approximate property size", "text", required=False)
                b.field(service, "cleaning_type", "Cleaning type", "select",
                        ["Regular", "Deep", "Move-in", "Move-out"], required=True)
            else:
                b.field(service, "area_notes", "Area size / details", "textarea", required=False)
                b.field(service, "cleaning_photos", "Upload area photos", "photo", required=False)

        # Distinct work entries rather than hiding specialist jobs inside ordinary packages.
        for title in ["Move-in Cleaning", "Move-out Cleaning", "Terrace Cleanup",
                      "Drain Area Cleaning", "Outdoor Floor Cleaning", "Glass Door Cleaning",
                      "Balcony Glass Cleaning", "Interior Glass Cleaning", "Tile Cleaning",
                      "Marble Floor Cleaning", "Marble Polishing", "Grout Cleaning"]:
            group = "Full Home Cleaning" if title in ["Move-in Cleaning", "Move-out Cleaning"] else (
                "Balcony & Terrace Cleaning" if title in ["Terrace Cleanup", "Drain Area Cleaning", "Outdoor Floor Cleaning"] else (
                    "Window & Glass Cleaning" if "Glass" in title else "Floor Cleaning"
                )
            )
            b.service(groups[group], title, f"{title}. Scope and equipment requirements are confirmed before booking.",
                      booking_mode="inspection" if title == "Marble Polishing" else "scheduled",
                      pricing_type="quote" if title == "Marble Polishing" else "fixed",
                      duration=90,
                      fields=[{"key": "area_size", "label": "Area size / quantity", "field_type": "text", "required": True},
                              {"key": "area_photos", "label": "Upload area photos", "field_type": "photo", "required": False}])
