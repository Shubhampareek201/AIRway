"""Geographic service-area resolution for customer addresses."""
from decimal import Decimal

from apps.core.models import Zone


def _point_in_ring(longitude, latitude, ring):
    """Ray-casting point-in-ring check; GeoJSON coordinates are [lon, lat]."""
    inside = False
    if not isinstance(ring, list) or len(ring) < 4:
        return False
    try:
        points = [(float(point[0]), float(point[1])) for point in ring]
    except (TypeError, ValueError, IndexError):
        return False
    x, y = float(longitude), float(latitude)
    j = len(points) - 1
    for i, (xi, yi) in enumerate(points):
        xj, yj = points[j]
        if ((yi > y) != (yj > y)):
            crossing_x = (xj - xi) * (y - yi) / ((yj - yi) or 1e-15) + xi
            if x < crossing_x:
                inside = not inside
        j = i
    return inside


def polygon_contains_point(geometry, longitude, latitude):
    """Support GeoJSON Polygon geometry including interior holes."""
    if not isinstance(geometry, dict) or geometry.get("type") != "Polygon":
        return False
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or not coordinates:
        return False
    if not _point_in_ring(longitude, latitude, coordinates[0]):
        return False
    return not any(
        _point_in_ring(longitude, latitude, hole)
        for hole in coordinates[1:]
    )


def resolve_active_zone(*, latitude, longitude):
    """Resolve coordinates to the single active polygon zone; fail closed otherwise."""
    matches = [
        zone for zone in Zone.objects.filter(
            is_active=True, city__is_active=True,
        ).select_related("city")
        if polygon_contains_point(zone.coverage_polygon, longitude, latitude)
    ]
    # Ambiguous overlapping polygons must never assign an address arbitrarily.
    return matches[0] if len(matches) == 1 else None
