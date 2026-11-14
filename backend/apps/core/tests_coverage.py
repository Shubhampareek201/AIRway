from django.test import SimpleTestCase


class PolygonCoverageTests(SimpleTestCase):
    def setUp(self):
        self.polygon = {
            "type": "Polygon",
            "coordinates": [[
                [75.55, 24.90],
                [75.65, 24.90],
                [75.65, 24.96],
                [75.55, 24.96],
                [75.55, 24.90],
            ]],
        }

    def test_point_inside_polygon_is_covered(self):
        from apps.core.coverage import polygon_contains_point
        self.assertTrue(polygon_contains_point(self.polygon, 75.60, 24.93))

    def test_point_outside_polygon_is_not_covered(self):
        from apps.core.coverage import polygon_contains_point
        self.assertFalse(polygon_contains_point(self.polygon, 75.70, 24.93))

    def test_point_inside_polygon_hole_is_not_covered(self):
        from apps.core.coverage import polygon_contains_point
        geometry = {
            "type": "Polygon",
            "coordinates": [
                self.polygon["coordinates"][0],
                [
                    [75.58, 24.92],
                    [75.62, 24.92],
                    [75.62, 24.94],
                    [75.58, 24.94],
                    [75.58, 24.92],
                ],
            ],
        }
        self.assertFalse(polygon_contains_point(geometry, 75.60, 24.93))

    def test_malformed_geometry_fails_closed(self):
        from apps.core.coverage import polygon_contains_point
        self.assertFalse(polygon_contains_point({"type": "MultiPolygon", "coordinates": []}, 75.6, 24.93))
        self.assertFalse(polygon_contains_point({"type": "Polygon", "coordinates": []}, 75.6, 24.93))

    def test_point_on_outer_boundary_is_included(self):
        from apps.core.coverage import polygon_contains_point
        self.assertTrue(polygon_contains_point(self.polygon, 75.55, 24.93))
