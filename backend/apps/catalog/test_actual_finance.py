from decimal import Decimal
from types import SimpleNamespace
from django.test import SimpleTestCase
from unittest.mock import patch
from apps.catalog.actual_finance import (
    _booking_payment_allocation,
    _booking_other_variable_cost_total,
    _booking_other_costs_reviewed,
    _money,
)

class BookingActualFinanceAllocationTests(SimpleTestCase):
    def test_legacy_booking_payment_allocation_uses_captured_tender(self):
        payment = SimpleNamespace(booking_id=17, order_id=None, amount=Decimal('280.00'), wallet_amount=Decimal('20.00'), raw_response={})
        self.assertEqual(_booking_payment_allocation(payment, SimpleNamespace(pk=17)), (Decimal('300.00'), Decimal('280.00'), True))

    def test_order_payment_uses_booking_specific_service_allocation(self):
        payment = SimpleNamespace(booking_id=None, order_id=4, amount=Decimal('500.00'), wallet_amount=Decimal('100.00'), raw_response={'service_allocation_v1': [{'booking_id': 17, 'total': '300.00', 'gateway_amount': '250.00'}, {'booking_id': 18, 'total': '300.00', 'gateway_amount': '150.00'}]})
        self.assertEqual(_booking_payment_allocation(payment, SimpleNamespace(pk=17)), (Decimal('300.00'), Decimal('250.00'), True))

    def test_missing_order_allocation_is_not_guessed(self):
        payment = SimpleNamespace(booking_id=None, order_id=4, amount=Decimal('100.00'), wallet_amount=Decimal('0.00'), raw_response={})
        self.assertEqual(_booking_payment_allocation(payment, SimpleNamespace(pk=17)), (Decimal('0.00'), Decimal('0.00'), False))

    def test_money_rounds_to_currency_precision(self):
        self.assertEqual(_money(Decimal('1.005')), Decimal('1.01'))


class BookingVariableCostReconciliationUnitTests(SimpleTestCase):
    @patch("apps.bookings.models.BookingVariableCost.objects.filter")
    def test_variable_costs_are_summed_without_rounding_away_cents(self, filter_mock):
        filter_mock.return_value.values_list.return_value = [
            Decimal("12.35"), Decimal("7.65"), Decimal("0.01"),
        ]
        total = _booking_other_variable_cost_total(SimpleNamespace(pk=17))
        self.assertEqual(total, Decimal("20.01"))
        filter_mock.assert_called_once_with(booking=SimpleNamespace(pk=17))

    @patch("apps.bookings.models.BookingFinanceReconciliation.objects.filter")
    def test_unreviewed_expenses_keep_finance_incomplete(self, filter_mock):
        filter_mock.return_value.first.return_value = None
        self.assertFalse(_booking_other_costs_reviewed(SimpleNamespace(pk=17)))

    @patch("apps.bookings.models.BookingFinanceReconciliation.objects.filter")
    def test_review_requires_flag_and_review_timestamp(self, filter_mock):
        reconciliation = SimpleNamespace(other_costs_reviewed=True, reviewed_at=None)
        filter_mock.return_value.first.return_value = reconciliation
        self.assertFalse(_booking_other_costs_reviewed(SimpleNamespace(pk=17)))
        reconciliation.reviewed_at = object()
        self.assertTrue(_booking_other_costs_reviewed(SimpleNamespace(pk=17)))


class ServiceProfitabilitySummaryTests(SimpleTestCase):
    @patch("apps.catalog.actual_finance.calculate_booking_actual_finance")
    @patch("apps.catalog.finance.calculate_estimated_contribution")
    def test_compares_only_complete_actuals_with_known_estimates(self, estimate_mock, actual_mock):
        from apps.catalog.actual_finance import summarize_service_profitability

        complete = SimpleNamespace(
            pricing_snapshot={"subtotal": "500.00"},
            worker_payout_snapshot={"total": "250.00"},
        )
        incomplete = SimpleNamespace(
            pricing_snapshot={"subtotal": "400.00"},
            worker_payout_snapshot={"total": "200.00"},
        )
        actual_mock.side_effect = [
            {"status": "complete", "partial_contribution": Decimal("180.00")},
            {"status": "incomplete", "partial_contribution": Decimal("0.00")},
        ]
        estimate_mock.return_value = Decimal("150.00")

        report = summarize_service_profitability([complete, incomplete], SimpleNamespace())

        self.assertEqual(report["booking_count"], 2)
        self.assertEqual(report["actual_complete_count"], 1)
        self.assertEqual(report["actual_incomplete_count"], 1)
        self.assertEqual(report["estimated_count"], 1)
        self.assertEqual(report["actual_contribution_total"], Decimal("180.00"))
        self.assertEqual(report["estimated_contribution_total"], Decimal("150.00"))
        self.assertEqual(report["variance"], Decimal("30.00"))
        self.assertEqual(report["profitability_status"], "Insufficient data")
        self.assertEqual(estimate_mock.call_count, 1)

    @patch("apps.catalog.actual_finance.calculate_booking_actual_finance")
    def test_missing_historical_price_or_payout_does_not_invent_estimate(self, actual_mock):
        from apps.catalog.actual_finance import summarize_service_profitability

        booking = SimpleNamespace(
            pricing_snapshot={"subtotal": "500.00"},
            worker_payout_snapshot={},
        )
        actual_mock.return_value = {
            "status": "complete",
            "partial_contribution": Decimal("100.00"),
        }
        report = summarize_service_profitability([booking], SimpleNamespace())
        self.assertEqual(report["actual_complete_count"], 1)
        self.assertEqual(report["estimated_count"], 0)
        self.assertIsNone(report["variance"])
        self.assertEqual(report["profitability_status"], "Insufficient data")

    @patch("apps.catalog.actual_finance.calculate_booking_actual_finance")
    @patch("apps.catalog.finance.calculate_estimated_contribution")
    def test_profitability_classification_requires_all_finance_and_estimates(self, estimate_mock, actual_mock):
        from apps.catalog.actual_finance import summarize_service_profitability

        booking = SimpleNamespace(
            pricing_snapshot={"subtotal": "500.00"},
            worker_payout_snapshot={"total": "250.00"},
        )
        actual_mock.return_value = {
            "status": "complete",
            "partial_contribution": Decimal("180.00"),
        }
        estimate_mock.return_value = Decimal("150.00")

        report = summarize_service_profitability([booking], SimpleNamespace())

        self.assertEqual(report["profitability_status"], "Profitable")
        self.assertEqual(report["actual_average"], Decimal("180.00"))
        self.assertEqual(report["estimated_average"], Decimal("150.00"))
