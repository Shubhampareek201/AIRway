from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.catalog.finance import (
    calculate_estimated_contribution,
    calculate_worker_payout,
)


class WorkerPayoutCalculationTests(SimpleTestCase):
    def setUp(self):
        self.service = SimpleNamespace(
            PricingType=SimpleNamespace(FIXED="fixed"),
            pricing_type="fixed",
            visit_fee_worker_payout=Decimal("80.00"),
            variants=SimpleNamespace(
                filter=lambda **kwargs: SimpleNamespace(exists=lambda: True)
            ),
        )
        self.variant = SimpleNamespace(worker_payout=Decimal("250.00"))
        self.addon = SimpleNamespace(worker_payout=Decimal("30.00"))

    def test_variant_addon_and_quantity_use_fixed_catalogue_payout(self):
        payout = calculate_worker_payout(
            service=self.service, variant=self.variant,
            addon_rows=[(self.addon, 2)], quantity=2,
            booking_mode="scheduled",
        )
        self.assertEqual(payout, Decimal("620.00"))

    def test_inspection_visit_payout_is_added_once(self):
        payout = calculate_worker_payout(
            service=self.service, variant=self.variant,
            addon_rows=[], quantity=3, booking_mode="inspection",
        )
        self.assertEqual(payout, Decimal("830.00"))

    def test_missing_variant_payout_is_not_guessed_from_customer_price(self):
        self.variant.worker_payout = None
        payout = calculate_worker_payout(
            service=self.service, variant=self.variant,
            addon_rows=[], quantity=1, booking_mode="scheduled",
        )
        self.assertIsNone(payout)

    def test_zero_payout_is_not_dispatchable(self):
        self.variant.worker_payout = Decimal("0.00")
        payout = calculate_worker_payout(
            service=self.service, variant=self.variant,
            addon_rows=[], quantity=1, booking_mode="scheduled",
        )
        self.assertIsNone(payout)


class ContributionEstimateTests(SimpleTestCase):
    def setUp(self):
        self.service = SimpleNamespace(
            estimated_gateway_fee_percent=Decimal("2.00"),
            tax_rate=Decimal("18.00"),
            discount_reserve_percent=Decimal("3.00"),
            rewards_reserve_percent=Decimal("1.00"),
            refund_reserve_percent=Decimal("2.00"),
            rework_reserve_percent=Decimal("1.00"),
            other_variable_cost_per_booking=Decimal("10.00"),
            minimum_contribution_floor=Decimal("50.00"),
            target_contribution_margin_percent=Decimal("10.00"),
        )

    def test_contribution_uses_configured_reserves_and_excludes_tax(self):
        value = calculate_estimated_contribution(
            customer_price=Decimal("1000.00"),
            worker_payout=Decimal("500.00"),
            service=self.service,
        )
        self.assertEqual(value, Decimal("396.40"))

    def test_missing_assumption_returns_no_estimate(self):
        self.service.refund_reserve_percent = None
        value = calculate_estimated_contribution(
            customer_price=Decimal("1000.00"),
            worker_payout=Decimal("500.00"),
            service=self.service,
        )
        self.assertIsNone(value)
