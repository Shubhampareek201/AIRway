from django import forms


class CoveragePolygonWidget(forms.Textarea):
    """Admin map editor for a GeoJSON Polygon service-area boundary."""

    template_name = "admin/widgets/coverage_polygon.html"

    class Media:
        css = {
            "all": (
                "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",
                "https://cdnjs.cloudflare.com/ajax/libs/leaflet.draw/1.0.4/leaflet.draw.css",
                "core/css/coverage_polygon_widget.css",
            )
        }
        js = (
            "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
            "https://cdnjs.cloudflare.com/ajax/libs/leaflet.draw/1.0.4/leaflet.draw.js",
            "core/js/coverage_polygon_widget.js",
        )

    def __init__(self, attrs=None):
        attrs = {**(attrs or {})}
        attrs.setdefault("rows", 4)
        attrs.setdefault("cols", 80)
        attrs.setdefault("class", "vLargeTextField airway-coverage-json")
        super().__init__(attrs)
