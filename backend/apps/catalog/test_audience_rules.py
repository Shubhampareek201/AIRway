from django.test import SimpleTestCase

from apps.catalog.audience import validate_beauty_audience


class BeautyAudienceRulesTest(SimpleTestCase):
    class Category:
        slug = "beauty"
        parent_id = None
        parent = None

    class Service:
        def __init__(self, audience):
            self.category = BeautyAudienceRulesTest.Category()
            self.audience = audience

    def test_men_section_only_accepts_men_services(self):
        validate_beauty_audience(self.Service("men"), {"beauty_audience": "men"})

    def test_men_section_rejects_unisex_services(self):
        with self.assertRaises(ValueError):
            validate_beauty_audience(self.Service("all"), {"beauty_audience": "men"})

    def test_women_section_only_accepts_women_services(self):
        validate_beauty_audience(self.Service("women"), {"beauty_audience": "women"})

    def test_women_section_rejects_unisex_services(self):
        with self.assertRaises(ValueError):
            validate_beauty_audience(self.Service("all"), {"beauty_audience": "women"})

    def test_unisex_section_only_accepts_all_services(self):
        validate_beauty_audience(self.Service("all"), {"beauty_audience": "both"})

    def test_unisex_section_rejects_gender_specific_services(self):
        with self.assertRaises(ValueError):
            validate_beauty_audience(self.Service("men"), {"beauty_audience": "both"})

    def test_beauty_audience_is_required_for_booking(self):
        with self.assertRaises(ValueError):
            validate_beauty_audience(self.Service("men"), {})
