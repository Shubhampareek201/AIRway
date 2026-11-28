"""Server-side road routing for customer booking tracking.

The Mapbox token is read only from backend settings and is never returned to clients.
Routing is optional: missing configuration or provider/network errors return None so
live GPS tracking continues without inventing a route or ETA.
"""
import json
import logging
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


def get_live_directions(origin_latitude, origin_longitude, destination_latitude, destination_longitude, cache_scope=None):
    token = getattr(settings, "MAPBOX_ACCESS_TOKEN", "")
    if not token:
        return None

    coordinates = (
        float(origin_longitude), float(origin_latitude),
        float(destination_longitude), float(destination_latitude),
    )
    if not all(-180 <= value <= 180 for value in (coordinates[0], coordinates[2])) or not all(
        -90 <= value <= 90 for value in (coordinates[1], coordinates[3])
    ):
        return None

    cache_key = (
        f"airway:mapbox:directions:booking:{cache_scope}"
        if cache_scope is not None
        else "airway:mapbox:directions:" + ":".join(f"{value:.5f}" for value in coordinates)
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return None if cached.get("unavailable") else cached

    params = urlencode({
        "access_token": token,
        "overview": "simplified",
        "geometries": "geojson",
        "steps": "false",
    })
    url = (
        "https://api.mapbox.com/directions/v5/mapbox/driving/"
        f"{coordinates[0]},{coordinates[1]};{coordinates[2]},{coordinates[3]}?{params}"
    )
    try:
        request = Request(url, headers={"User-Agent": "AIRway/1.0"})
        with urlopen(request, timeout=4) as response:
            payload = json.loads(response.read(1_000_000).decode("utf-8"))
        routes = payload.get("routes") or []
        if not routes:
            cache.set(cache_key, {"unavailable": True}, timeout=20)
            return None
        route = routes[0]
        raw_coordinates = (route.get("geometry") or {}).get("coordinates") or []
        points = [
            [float(latitude), float(longitude)]
            for longitude, latitude in raw_coordinates
            if -180 <= float(longitude) <= 180 and -90 <= float(latitude) <= 90
        ]
        if len(points) < 2:
            cache.set(cache_key, None, timeout=15)
            return None
        result = {
            "coordinates": points,
            "duration_seconds": max(0, int(route.get("duration", 0))),
            "distance_meters": max(0, int(route.get("distance", 0))),
            "source": "mapbox",
        }
        cache.set(cache_key, result, timeout=60)
        return result
    except Exception:
        cache.set(cache_key, {"unavailable": True}, timeout=20)
        logger.warning("Mapbox directions unavailable for live booking tracking", exc_info=True)
        return None
