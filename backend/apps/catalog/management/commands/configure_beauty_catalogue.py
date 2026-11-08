from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.catalog.models import AddOn, Category, FormField, Service, ServiceVariant


# This is an admin staging catalogue, not a public launch switch. New services
# and packages are created inactive with zero prices. Admin must verify scope,
# provider capability, images, duration and rates before publishing them.
BEAUTY_CATALOGUE = {
    "Grooming & Massage": [
        {
            "title": "Men's Face Cleanup",
            "audience": "men",
            "description": "Basic face cleansing and grooming for men. Confirm products and steps in the selected package.",
            "duration": 45,
            "packages": [
                ("Essential Cleanup", ["Cleanse", "Exfoliation", "Mask", "Moisturiser"], 45),
                ("Deep Cleansing Cleanup", ["Cleanse", "Exfoliation", "Blackhead care where suitable", "Mask", "Moisturiser"], 60),
            ],
            "questions": [
                ("skin_type", "How would you describe your skin?", "select", ["Oily", "Dry", "Combination", "Sensitive", "Not sure"], False),
                ("skin_sensitivity", "Any known skin sensitivity or product allergy?", "textarea", [], False),
            ],
        },
        {
            "title": "Men's Detan Treatment",
            "audience": "men",
            "description": "Detan treatment for face, neck or other selected areas. Suitability and products must be confirmed by the professional.",
            "duration": 45,
            "packages": [("Face & Neck Detan", ["Skin assessment", "Detan application", "After-care"], 45), ("Face, Neck & Arms Detan", ["Skin assessment", "Detan application on selected areas", "After-care"], 60)],
            "questions": [("detan_areas", "Which areas would you like treated?", "select", ["Face", "Face & Neck", "Face, Neck & Arms"], True)],
        },
        {
            "title": "Men's Blackhead Removal",
            "audience": "men",
            "description": "Targeted blackhead care. Extraction is performed only when suitable and safe for the skin.",
            "duration": 40,
            "packages": [("Nose & T-zone", ["Cleanse", "Nose and T-zone blackhead care", "Soothing finish"], 40), ("Full Face Blackhead Care", ["Cleanse", "Suitable blackhead care", "Soothing finish"], 55)],
        },
        {
            "title": "Men's Facial",
            "audience": "men",
            "description": "Facial care selected for the customer's skin needs. Products and exact inclusions are admin-configured per package.",
            "duration": 60,
            "packages": [("Express Facial", ["Cleanse", "Exfoliation", "Mask", "Moisturiser"], 45), ("Deep Clean Facial", ["Cleanse", "Exfoliation", "Deep cleansing", "Mask", "Moisturiser"], 60), ("Premium Hydrating Facial", ["Skin assessment", "Hydrating facial steps", "Mask", "Moisturiser"], 75)],
            "questions": [("skin_type", "How would you describe your skin?", "select", ["Oily", "Dry", "Combination", "Sensitive", "Not sure"], False)],
        },
        {
            "title": "Men's Head & Shoulder Massage",
            "audience": "men",
            "description": "Relaxation massage focused on the head, neck and shoulders.",
            "duration": 30,
            "packages": [("30-minute Relaxation", ["Head massage", "Neck and shoulder massage"], 30), ("45-minute Relaxation", ["Extended head, neck and shoulder massage"], 45)],
        },
        {
            "title": "Men's Manicure",
            "audience": "men",
            "description": "Nail and hand grooming with clean, hygienic tools.",
            "duration": 40,
            "packages": [("Classic Manicure", ["Nail shaping", "Cuticle care", "Hand massage", "Moisturiser"], 40), ("Premium Manicure", ["Classic manicure", "Exfoliation", "Hand mask"], 55)],
        },
        {
            "title": "Men's Pedicure",
            "audience": "men",
            "description": "Foot and nail grooming with clean, hygienic tools.",
            "duration": 45,
            "packages": [("Classic Pedicure", ["Foot soak", "Nail shaping", "Foot care", "Moisturiser"], 45), ("Premium Pedicure", ["Classic pedicure", "Exfoliation", "Foot mask"], 60)],
        },
        {
            "title": "Groom Wedding Package",
            "audience": "men",
            "description": "A groom-preparation plan with separately selectable grooming services. Admin must configure the exact inclusions and event lead time.",
            "duration": 180,
            "packages": [("Groom Essential", ["Haircut and styling", "Beard grooming", "Face cleanup"], 150), ("Groom Premium", ["Haircut and styling", "Beard grooming", "Facial", "Manicure", "Pedicure"], 240), ("Groom Luxury", ["Premium haircut and styling", "Beard grooming", "Premium facial", "Manicure", "Pedicure", "Head and shoulder massage"], 300)],
            "questions": [
                ("event_date", "When is the wedding?", "text", [], True),
                ("groom_event_type", "What are you preparing for?", "select", ["Wedding day", "Engagement", "Pre-wedding function", "Other"], True),
                ("reference_photos", "Any reference style? Share a photo URL with the team.", "photo", [], False),
            ],
        },
    ],
    "Facial & Skin Care": [
        {
            "title": "Women's Blackhead Removal",
            "audience": "women",
            "description": "Targeted blackhead care with skin-suitability checks before treatment.",
            "duration": 40,
            "packages": [("Nose & T-zone", ["Cleanse", "Suitable blackhead care", "Soothing finish"], 40), ("Full Face Blackhead Care", ["Cleanse", "Suitable blackhead care", "Soothing finish"], 55)],
        },
        {
            "title": "Women's Detan Treatment",
            "audience": "women",
            "description": "Detan treatment for selected areas. Products and suitability must be confirmed by the professional.",
            "duration": 45,
            "packages": [("Face & Neck Detan", ["Skin assessment", "Detan application", "After-care"], 45), ("Face, Neck & Arms Detan", ["Skin assessment", "Detan application on selected areas", "After-care"], 60)],
        },
        {
            "title": "Women's Skin Consultation",
            "audience": "women",
            "description": "Discuss skin goals and sensitivities with a qualified beauty professional before choosing a suitable service.",
            "duration": 20,
            "packages": [("Consultation", ["Discuss skin goals", "Review sensitivities", "Recommend suitable salon services"], 20)],
            "questions": [("skin_goals", "What would you like help with?", "select", ["Hydration", "Dullness", "Tan", "Uneven texture", "Blackheads", "Not sure"], True), ("skin_sensitivity", "Known allergies or sensitivities", "textarea", [], False)],
        },
    ],
    "Hair Services": [
        {
            "title": "Women's Hair Consultation",
            "audience": "women",
            "description": "Discuss hair goals, hair history and treatment suitability before selecting a chemical or styling service.",
            "duration": 20,
            "packages": [("Hair Consultation", ["Discuss hair goals", "Review hair history", "Explain suitable options"], 20)],
            "questions": [("hair_goal", "What is your main hair goal?", "select", ["Hair repair", "Smoothening", "Straightening", "Colour", "Volume", "Not sure"], True), ("hair_length", "Current hair length", "select", ["Short", "Shoulder length", "Mid-back", "Long"], False), ("hair_history", "Previous colour or chemical treatments", "textarea", [], False)],
        },
        {
            "title": "Women's Hair Spa & Repair",
            "audience": "women",
            "description": "Hair and scalp care with treatment choice based on hair condition and provider capability.",
            "duration": 75,
            "packages": [("Nourishing Hair Spa", ["Hair and scalp assessment", "Nourishing treatment", "Rinse and finish"], 60), ("Deep Repair Hair Spa", ["Hair assessment", "Deep conditioning treatment", "Scalp care", "Rinse and finish"], 75), ("Premium Hair Repair", ["Hair assessment", "Premium repair treatment", "Conditioning", "Blow dry"], 90)],
            "questions": [("hair_concern", "What is your main hair concern?", "select", ["Dryness", "Frizz", "Damage", "Hair fall concern", "Dandruff concern", "General care"], True), ("hair_length", "Hair length", "select", ["Short", "Shoulder length", "Mid-back", "Long"], True)],
        },
    ],
    "Makeup & Occasion Styling": [
        {
            "title": "Pre-Bridal Care Package",
            "audience": "women",
            "description": "A multi-visit pre-bridal plan. Admin must configure visit count, included services, schedule and package price before activation.",
            "duration": 120,
            "packages": [("Pre-Bridal Essential", ["Consultation", "Facial session", "Hair spa session", "Manicure and pedicure"], 120), ("Pre-Bridal Premium", ["Consultation", "Facial sessions", "Hair spa sessions", "Cleanup", "Manicure and pedicure", "Threading and waxing as selected"], 180), ("Pre-Bridal Luxury", ["Personalised consultation", "Premium skin care sessions", "Hair repair sessions", "Manicure and pedicure", "Event preparation consultation"], 240)],
            "questions": [("event_date", "When is the wedding or event?", "text", [], True), ("event_city", "Where will the event take place?", "text", [], False), ("bridal_goals", "What would you like included?", "textarea", [], False)],
        },
        {
            "title": "Bridal Makeup Consultation",
            "audience": "women",
            "description": "Discuss the bridal look, event schedule, skin sensitivities and trial requirements before a quote is prepared.",
            "duration": 30,
            "packages": [("Bridal Consultation", ["Discuss event schedule", "Discuss makeup style", "Discuss trial and preparation"], 30)],
            "questions": [("event_date", "Wedding date", "text", [], True), ("event_venue", "Event venue or area", "text", [], True), ("makeup_style", "Preferred makeup style", "select", ["Natural", "Soft glam", "Traditional", "HD", "Not sure"], False), ("reference_photos", "Reference look photo URL", "photo", [], False)],
        },
        {
            "title": "Bridal Hairstyle",
            "audience": "women",
            "description": "Bridal hairstyle consultation and styling. Final style and timing are agreed before confirmation.",
            "duration": 90,
            "packages": [("Bridal Hairstyle", ["Hair preparation", "Selected bridal hairstyle", "Finishing"], 90)],
            "questions": [("event_date", "Event date", "text", [], True), ("hair_length", "Hair length", "select", ["Short", "Shoulder length", "Mid-back", "Long"], True), ("reference_photos", "Reference hairstyle photo URL", "photo", [], False)],
        },
        {
            "title": "Saree Draping",
            "audience": "women",
            "description": "Saree draping for weddings, parties and special occasions.",
            "duration": 30,
            "packages": [("Standard Draping", ["Saree draping and pleat setting"], 30), ("Premium Draping", ["Detailed draping", "Pleat setting", "Pallu styling"], 45)],
            "questions": [("event_date", "Event date", "text", [], False), ("saree_type", "Saree type", "select", ["Regular", "Silk", "Designer", "Pre-stitched", "Not sure"], False)],
        },
    ],
    "Manicure & Pedicure": [
        {
            "title": "Unisex Classic Manicure",
            "audience": "all",
            "description": "Classic hand and nail grooming available to all customers.",
            "duration": 40,
            "packages": [("Classic Manicure", ["Nail shaping", "Cuticle care", "Hand massage", "Moisturiser"], 40)],
        },
        {
            "title": "Unisex Classic Pedicure",
            "audience": "all",
            "description": "Classic foot and nail grooming available to all customers.",
            "duration": 45,
            "packages": [("Classic Pedicure", ["Foot soak", "Nail shaping", "Foot care", "Moisturiser"], 45)],
        },
    ],
}


class Command(BaseCommand):
    help = (
        "Stage additional AIRway Beauty services and packages for Admin review. "
        "New records are inactive and unpriced; this command never publishes them."
    )

    def handle(self, *args, **options):
        created = {"categories": 0, "services": 0, "packages": 0, "questions": 0}
        root = Category.objects.filter(slug="beauty", parent__isnull=True).first()
        if root is None:
            self.stderr.write(self.style.ERROR("Beauty root category not found. Run seed_launch_catalogue first."))
            return

        for category_title, service_rows in BEAUTY_CATALOGUE.items():
            category, category_created = Category.objects.get_or_create(
                parent=root,
                slug=__import__("django.utils.text", fromlist=["slugify"]).slugify(category_title),
                defaults={"title": category_title, "is_active": True},
            )
            if category_created:
                created["categories"] += 1

            for row in service_rows:
                service, service_created = Service.objects.get_or_create(
                    category=category,
                    title=row["title"],
                    defaults={
                        "description": row["description"],
                        "audience": row["audience"],
                        "duration_minutes": row["duration"],
                        "is_active": False,
                        "is_popular": False,
                        "visit_fee": Decimal("0.00"),
                    },
                )
                if service_created:
                    created["services"] += 1

                for index, package_row in enumerate(row.get("packages", []), start=1):
                    title, tasks, duration = package_row
                    _variant, variant_created = ServiceVariant.objects.get_or_create(
                        service=service,
                        title=title,
                        defaults={
                            "description": f"{title}. Admin: verify products, exact scope and provider capability before activation.",
                            "included_tasks": tasks,
                            "duration_minutes": duration,
                            "mrp": Decimal("0.00"),
                            "price": Decimal("0.00"),
                            "sort_order": index,
                            "is_active": False,
                        },
                    )
                    if variant_created:
                        created["packages"] += 1

                for index, question in enumerate(row.get("questions", []), start=1):
                    key, label, field_type, choices, required = question
                    _field, field_created = FormField.objects.get_or_create(
                        service=service,
                        key=key,
                        defaults={
                            "label": label,
                            "field_type": field_type,
                            "options": choices,
                            "is_required": required,
                            "is_active": True,
                            "sort_order": index,
                        },
                    )
                    if field_created:
                        created["questions"] += 1

        self.stdout.write(self.style.SUCCESS(
            "Beauty catalogue staged (no services published): " +
            ", ".join(f"{key}={value}" for key, value in created.items())
        ))
        self.stdout.write(
            "Before activation, Admin must add images, verify service scope and inclusions, "
            "set real INR prices and durations, and confirm approved workers and city coverage."
        )
        self.stdout.write("Safe to rerun: existing Admin edits are never overwritten.")
