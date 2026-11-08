from rest_framework import serializers
from .models import Banner, Category, CategoryAudienceOption, Service, ServiceVariant, AddOn, FormField, ServiceImage


class CategoryAudienceOptionSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = CategoryAudienceOption
        fields = ["id", "audience", "title", "subtitle", "image", "sort_order", "is_active"]

    def get_image(self, obj):
        if not obj.image:
            return None
        request = self.context.get("request")
        url = obj.image.url
        return request.build_absolute_uri(url) if request else url


class CategoryTreeSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    audience_options = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "title", "title_hi", "slug", "image", "audience_options", "flow_steps", "is_active", "parent", "children"]
        read_only_fields = ["slug", "children"]

    def get_audience_options(self, obj):
        options = obj.audience_options.filter(is_active=True)
        return CategoryAudienceOptionSerializer(
            options, many=True, context=self.context
        ).data

    def get_image(self, obj):
        # Category tiles must use the category's own uploaded image.
        # Never borrow an arbitrary first service image: that can show a
        # kitchen photo on a bathroom category or vice versa.
        if not obj.image:
            return None
        request = self.context.get("request")
        url = obj.image.url
        return request.build_absolute_uri(url) if request else url

    def get_children(self, obj):
        children = obj.children.filter(is_active=True)
        visible_ids = self.context.get("visible_category_ids")
        if visible_ids is not None:
            children = children.filter(id__in=visible_ids)
        children = children.order_by("sort_order", "title")
        return CategoryTreeSerializer(children, many=True, context=self.context).data


class CategorySerializer(serializers.ModelSerializer):
    audience_options = serializers.SerializerMethodField()

    def get_audience_options(self, obj):
        options = obj.audience_options.filter(is_active=True)
        return CategoryAudienceOptionSerializer(
            options, many=True, context=self.context
        ).data

    class Meta:
        model = Category
        fields = ["id", "title", "title_hi", "slug", "image", "audience_options", "is_active", "parent"]
        read_only_fields = ["slug"]


class ServiceImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceImage
        fields = ["id", "image", "sort_order"]


class ServiceVariantSerializer(serializers.ModelSerializer):
    discount_percent = serializers.IntegerField(read_only=True)
    duration_minutes = serializers.IntegerField(required=False, allow_null=True)

    class Meta:
        model = ServiceVariant
        fields = ["id", "title", "title_hi", "description", "included_tasks", "image", "attributes", "mrp", "price", "discount_percent", "duration_minutes", "sort_order", "is_active"]
        read_only_fields = ["discount_percent"]


class AddOnSerializer(serializers.ModelSerializer):
    discount_percent = serializers.IntegerField(read_only=True)

    class Meta:
        model = AddOn
        fields = ["id", "title", "title_hi", "description", "image", "mrp", "price", "discount_percent", "sort_order", "is_active"]
        read_only_fields = ["discount_percent"]


class FormFieldSerializer(serializers.ModelSerializer):
    field_type_display = serializers.CharField(source="get_field_type_display", read_only=True)

    class Meta:
        model = FormField
        fields = ["id", "key", "label", "label_hi", "field_type", "field_type_display", "options", "is_required", "visibility_rules", "sort_order"]
        read_only_fields = ["field_type_display"]


class ServiceSerializer(serializers.ModelSerializer):
    is_available = serializers.SerializerMethodField()
    booking_mode_display = serializers.CharField(source="get_booking_mode_display", read_only=True)
    pricing_type_display = serializers.CharField(source="get_pricing_type_display", read_only=True)
    audience_display = serializers.CharField(source="get_audience_display", read_only=True)
    images = ServiceImageSerializer(many=True, read_only=True)
    variants = ServiceVariantSerializer(many=True, read_only=True)
    addons = AddOnSerializer(many=True, read_only=True)
    form_fields = FormFieldSerializer(many=True, read_only=True)
    category_name = serializers.CharField(source="category.title", read_only=True)
    category_slug = serializers.CharField(source="category.slug", read_only=True)

    def get_is_available(self, obj):
        available_ids = self.context.get("available_service_ids")
        # Requests without a selected address retain the existing general
        # catalogue behaviour; address-scoped requests get a real availability flag.
        return True if available_ids is None else obj.id in available_ids

    def get_supports_professional_preference(self, obj):
        category = obj.category
        while category.parent_id:
            category = category.parent
        return "beauty" in (category.slug or "").lower() or "beauty" in (category.title or "").lower()

    supports_professional_preference = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = [
            "id", "category", "category_name", "category_slug", "title", "title_hi", "description",
            "is_available",
            "image", "booking_mode", "booking_mode_display", "pricing_type", "pricing_type_display",
            "unit_label", "visit_fee", "duration_minutes", "buffer_minutes",
            "audience", "audience_display", "requires_female_worker", "supports_professional_preference",
            "is_popular", "sort_order", "is_active",
            "images", "variants", "addons", "form_fields",
            "created_at", "updated_at"
        ]


class BannerSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(read_only=True)
    link_service = serializers.IntegerField(source="link_service_id", read_only=True)

    class Meta:
        model = Banner
        fields = ["id", "title", "image", "link_service", "sort_order"]
