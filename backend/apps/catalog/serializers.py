from rest_framework import serializers
from .models import Category, Service, ServiceVariant, AddOn, FormField, ServiceImage


class CategoryTreeSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "title", "title_hi", "slug", "image", "is_active", "parent", "children"]
        read_only_fields = ["slug", "children"]

    def get_children(self, obj):
        children = obj.children.filter(is_active=True).order_by("sort_order", "title")
        return CategoryTreeSerializer(children, many=True, context=self.context).data


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "title", "title_hi", "slug", "image", "is_active", "parent"]
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
        fields = ["id", "title", "title_hi", "mrp", "price", "discount_percent", "duration_minutes", "sort_order", "is_active"]
        read_only_fields = ["discount_percent"]


class AddOnSerializer(serializers.ModelSerializer):
    discount_percent = serializers.IntegerField(read_only=True)

    class Meta:
        model = AddOn
        fields = ["id", "title", "title_hi", "mrp", "price", "discount_percent", "sort_order", "is_active"]
        read_only_fields = ["discount_percent"]


class FormFieldSerializer(serializers.ModelSerializer):
    field_type_display = serializers.CharField(source="get_field_type_display", read_only=True)

    class Meta:
        model = FormField
        fields = ["id", "key", "label", "label_hi", "field_type", "field_type_display", "options", "is_required", "sort_order"]
        read_only_fields = ["field_type_display"]


class ServiceSerializer(serializers.ModelSerializer):
    booking_mode_display = serializers.CharField(source="get_booking_mode_display", read_only=True)
    pricing_type_display = serializers.CharField(source="get_pricing_type_display", read_only=True)
    audience_display = serializers.CharField(source="get_audience_display", read_only=True)
    images = ServiceImageSerializer(many=True, read_only=True)
    variants = ServiceVariantSerializer(many=True, read_only=True)
    addons = AddOnSerializer(many=True, read_only=True)
    form_fields = FormFieldSerializer(many=True, read_only=True)
    category_name = serializers.CharField(source="category.title", read_only=True)
    category_slug = serializers.CharField(source="category.slug", read_only=True)

    class Meta:
        model = Service
        fields = [
            "id", "category", "category_name", "category_slug", "title", "title_hi", "description",
            "image", "booking_mode", "booking_mode_display", "pricing_type", "pricing_type_display",
            "unit_label", "visit_fee", "duration_minutes", "buffer_minutes",
            "audience", "audience_display", "requires_female_worker",
            "is_popular", "sort_order", "is_active",
            "images", "variants", "addons", "form_fields",
            "created_at", "updated_at"
        ]
