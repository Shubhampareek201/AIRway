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
        self.assertEqual(report["estimated_count"], 2)
        self.assertEqual(report["actual_contribution_total"], Decimal("180.00"))
        self.assertEqual(report["estimated_contribution_total"], Decimal("300.00"))
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

    def test_combined_category_summary_preserves_totals_and_requires_complete_data(self):
        from apps.catalog.actual_finance import combine_profitability_summaries

        first = {
            "booking_count": 2, "actual_complete_count": 1, "actual_incomplete_count": 1,
            "estimated_count": 1, "actual_contribution_total": Decimal("100.00"),
            "estimated_contribution_total": Decimal("80.00"),
            "comparable_actual_total": Decimal("100.00"),
            "comparable_estimated_total": Decimal("80.00"),
        }
        second = {
            "booking_count": 1, "actual_complete_count": 1, "actual_incomplete_count": 0,
            "estimated_count": 1, "actual_contribution_total": Decimal("50.00"),
            "estimated_contribution_total": Decimal("40.00"),
            "comparable_actual_total": Decimal("50.00"),
            "comparable_estimated_total": Decimal("40.00"),
        }
        result = combine_profitability_summaries([first, second])
        self.assertEqual(result["booking_count"], 3)
        self.assertEqual(result["actual_contribution_total"], Decimal("150.00"))
        self.assertEqual(result["estimated_contribution_total"], Decimal("120.00"))
        self.assertEqual(result["variance"], Decimal("30.00"))
        self.assertEqual(result["profitability_status"], "Insufficient data")

    def test_profitability_admin_templates_are_discoverable(self):
        from django.template.loader import get_template

        get_template("admin/catalog/service/profitability_report.html")
        get_template("admin/catalog/service/change_list.html")

    @patch("apps.catalog.actual_finance.calculate_booking_actual_finance")
    @patch("apps.catalog.finance.calculate_estimated_contribution")
    def test_estimate_is_counted_even_when_actual_finance_is_incomplete(self, estimate_mock, actual_mock):
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
        estimate_mock.side_effect = [Decimal("150.00"), Decimal("120.00")]

        report = summarize_service_profitability([complete, incomplete], SimpleNamespace())

        self.assertEqual(report["booking_count"], 2)
        self.assertEqual(report["actual_complete_count"], 1)
        self.assertEqual(report["actual_incomplete_count"], 1)
        self.assertEqual(report["estimated_count"], 2)
        self.assertEqual(report["estimated_contribution_total"], Decimal("270.00"))
        self.assertEqual(report["estimated_average"], Decimal("135.00"))
        self.assertEqual(report["variance"], Decimal("30.00"))
        self.assertEqual(report["profitability_status"], "Insufficient data")
    def test_admin_can_add_append_only_cost_and_new_cost_invalidates_review(self):
        from apps.bookings.models import BookingFinanceReconciliation, BookingVariableCost

        BookingFinanceReconciliation.objects.create(
            booking=self.booking,
            other_costs_reviewed=True,
            review_note="Reviewed all expenses",
            reviewed_by=self.admin_user,
            reviewed_at=timezone.now(),
        )
        self.client.force_login(self.admin_user)
        add_url = reverse("admin:bookings_bookingvariablecost_add")
        response = self.client.get(add_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="amount"')
        self.assertContains(response, 'name="description"')

        response = self.client.post(
            add_url,
            {
                "booking": str(self.booking.pk),
                "category": BookingVariableCost.Category.TRAVEL,
                "amount": "25.50",
                "description": "Worker travel expense",
                "reference": "TRAVEL-001",
            },
        )
        self.assertEqual(response.status_code, 302)
        cost = BookingVariableCost.objects.get(reference="TRAVEL-001")
        self.assertEqual(cost.created_by, self.admin_user)
        self.assertEqual(cost.amount, Decimal("25.50"))

        reconciliation = BookingFinanceReconciliation.objects.get(booking=self.booking)
        self.assertFalse(reconciliation.other_costs_reviewed)
        self.assertIsNone(reconciliation.reviewed_by)
        self.assertIsNone(reconciliation.reviewed_at)

        change_url = reverse("admin:bookings_bookingvariablecost_change", args=[cost.pk])
        self.assertEqual(self.client.get(change_url).status_code, 403)


from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone


class ServiceProfitabilityAdminReportIntegrationTests(TestCase):
    def setUp(self):
        from apps.accounts.models import Address, User
        from apps.bookings.models import Booking
        from apps.catalog.models import Category, Service

        self.customer = User.objects.create_user(
            phone="+919876543210", password="test-password"
        )
        self.admin_user = User.objects.create_superuser(
            phone="+919876543211", password="test-password"
        )
        self.address = Address.objects.create(
            user=self.customer,
            house_details="Test House",
            landmark="Test Landmark",
            full_address="Test Address, Rawatbhata",
        )
        self.category = Category.objects.create(
            title="Cleaning", slug="profitability-cleaning"
        )
        self.service = Service.objects.create(
            category=self.category,
            title="Home Cleaning",
            booking_mode=Service.BookingMode.SCHEDULED,
            pricing_type=Service.PricingType.FIXED,
        )
        self.today = timezone.localdate()
        self.booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=timezone.now(),
            completed_at=timezone.now(),
            status=Booking.Status.COMPLETED,
            pricing_snapshot={"subtotal": "500.00"},
            worker_payout_snapshot={"total": "250.00"},
        )
        Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=timezone.now() - timedelta(days=10),
            completed_at=timezone.now() - timedelta(days=10),
            status=Booking.Status.COMPLETED,
            pricing_snapshot={"subtotal": "300.00"},
            worker_payout_snapshot={"total": "150.00"},
        )

    @patch("apps.catalog.actual_finance.calculate_booking_actual_finance")
    @patch("apps.catalog.finance.calculate_estimated_contribution")
    def test_admin_report_route_applies_completion_date_filters(
        self, estimate_mock, actual_mock
    ):
        estimate_mock.return_value = Decimal("150.00")
        actual_mock.return_value = {
            "status": "complete",
            "partial_contribution": Decimal("180.00"),
        }
        self.client.force_login(self.admin_user)

        response = self.client.get(
            reverse("admin:catalog_service_profitability_report"),
            {
                "start_date": self.today.isoformat(),
                "end_date": self.today.isoformat(),
                "category": str(self.category.pk),
                "service": str(self.service.pk),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["service_rows"]), 1)
        summary = response.context["service_rows"][0]["summary"]
        self.assertEqual(summary["booking_count"], 1)
        self.assertEqual(summary["actual_contribution_total"], Decimal("180.00"))
        self.assertEqual(summary["estimated_contribution_total"], Decimal("150.00"))
        self.assertContains(response, "Service profitability report")
        self.assertContains(response, "Home Cleaning")
