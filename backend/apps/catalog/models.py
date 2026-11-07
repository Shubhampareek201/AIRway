from django.db import models
from django.db.models import F, Q
from simple_history.models import HistoricalRecords

from apps.core.models import City, TimeStampedModel


class Category(TimeStampedModel):
    """Main title (Car Wash, Electrical...) aur uske sub-category (parent se)."""
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children"
    )
    title = models.CharField(max_length=100)
    title_hi = models.CharField("Title (Hindi)", max_length=100, blank=True)
    slug = models.SlugField(unique=True)
    image = models.ImageField(upload_to="categories/", blank=True)
    flow_steps = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Optional customer decision steps shown before browsing this category. "
            "Each item: key, title, type (select/text/number/textarea), options, required, description."
        ),
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["sort_order", "title"]

    def __str__(self):
        return f"{self.parent.title} > {self.title}" if self.parent else self.title


class Service(TimeStampedModel):
    class BookingMode(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled (slot book karo)"
        INSPECTION = "inspection", "Inspection -> Quote"
        PICKUP_DROP = "pickup_drop", "Pickup & Drop (baad mein)"

    class PricingType(models.TextChoices):
        FIXED = "fixed", "Fixed price"
        PER_UNIT = "per_unit", "Per unit (jaise per sq ft)"
        QUOTE = "quote", "Quote ke baad"

    class Audience(models.TextChoices):
        ALL = "all", "Sab"
        MEN = "men", "Men"
        WOMEN = "women", "Women"

    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="services")
    title = models.CharField(max_length=150)
    title_hi = models.CharField("Title (Hindi)", max_length=150, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="services/", blank=True)

    booking_mode = models.CharField(max_length=15, choices=BookingMode.choices, default=BookingMode.SCHEDULED)
    pricing_type = models.CharField(max_length=10, choices=PricingType.choices, default=PricingType.FIXED)
    unit_label = models.CharField(max_length=30, blank=True, help_text="Per unit ho toh: sq ft, room, item")
    visit_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0, help_text="Inspection/visit charge")

    duration_minutes = models.PositiveIntegerField(default=60)
    buffer_minutes = models.PositiveIntegerField(default=30, help_text="Do kaam ke beech travel/gap")

    audience = models.CharField(max_length=10, choices=Audience.choices, default=Audience.ALL)
    requires_female_worker = models.BooleanField(default=False)

    is_popular = models.BooleanField(default=False, help_text="Home page par 'Popular' mein dikhao")
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["sort_order", "title"]

    def __str__(self):
        return self.title


class ServiceImage(TimeStampedModel):
    """Ek service ke multiple images, app mein slider ki tarah chalenge."""
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="service_gallery/")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]


class PricedItem(TimeStampedModel):
    """Variant aur AddOn dono ka common price logic."""
    title = models.CharField(max_length=150)
    title_hi = models.CharField("Title (Hindi)", max_length=150, blank=True)
    description = models.TextField(blank=True, help_text="What is included in this package or add-on")
    mrp = models.DecimalField("MRP (kata hua)", max_digits=10, decimal_places=2)
    price = models.DecimalField("Selling price", max_digits=10, decimal_places=2)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True
        ordering = ["sort_order", "price"]

    @property
    def discount_percent(self):
        if self.mrp and self.mrp > self.price:
            return int(round((self.mrp - self.price) * 100 / self.mrp))
        return 0

    def __str__(self):
        return self.title


class ServiceVariant(PricedItem):
    """Package/size: Basic, Premium, Hatchback, SUV, 1 BHK..."""
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="variants")
    duration_minutes = models.PositiveIntegerField(null=True, blank=True, help_text="Khali = service wala time")
    history = HistoricalRecords()

    class Meta(PricedItem.Meta):
        constraints = [
            models.CheckConstraint(condition=Q(price__lte=F("mrp")), name="variant_price_lte_mrp")
        ]

    def __str__(self):
        return f"{self.service.title} - {self.title}"


class AddOn(PricedItem):
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="addons")
    history = HistoricalRecords()

    class Meta(PricedItem.Meta):
        constraints = [
            models.CheckConstraint(condition=Q(price__lte=F("mrp")), name="addon_price_lte_mrp")
        ]


class FormField(TimeStampedModel):
    """Service ke custom sawaal. Naya sawaal = admin mein ek row, code change nahi."""
    class FieldType(models.TextChoices):
        TEXT = "text", "Text"
        TEXTAREA = "textarea", "Lamba text"
        NUMBER = "number", "Number"
        SELECT = "select", "Dropdown"
        PHOTO = "photo", "Photo"

    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="form_fields")
    key = models.SlugField(help_text="Jaise: car_type, area_sqft, problem")
    label = models.CharField(max_length=150)
    label_hi = models.CharField("Label (Hindi)", max_length=150, blank=True)
    field_type = models.CharField(max_length=10, choices=FieldType.choices)
    options = models.JSONField(default=list, blank=True, help_text='Dropdown ke liye: ["Sedan", "SUV"]')
    is_active = models.BooleanField(default=True, help_text="Admin sawaal ko form mein chhod sakta hai")
    is_required = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]
        constraints = [
            models.UniqueConstraint(fields=["service", "key"], name="unique_field_key_per_service")
        ]


class CityService(TimeStampedModel):
    """Kaunsi service kis city mein on hai. Worker nahi toh admin yahan off rakhega."""
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name="city_services")
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="city_services")
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["city", "service"], name="unique_city_service")]

    def __str__(self):
        return f"{self.service.title} @ {self.city.name}"


class Banner(TimeStampedModel):
    title = models.CharField(max_length=150)
    image = models.ImageField(upload_to="banners/")
    link_service = models.ForeignKey(Service, null=True, blank=True, on_delete=models.SET_NULL)
    city = models.ForeignKey(City, null=True, blank=True, on_delete=models.CASCADE)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return self.title