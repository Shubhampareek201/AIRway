from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from .lifecycle import (
    PaymentLifecycleError,
    calculate_customer_refund,
    calculate_platform_refund,
    cancellation_cutoff,
    customer_cancellation_is_refundable,
    split_total,
)


class SplitPaymentCalculationTests(SimpleTestCase):
    def test_even_total_is_split_equally(self):
        self.assertEqual(split_total("1000.00"), (Decimal("500.00"), Decimal("500.00")))

    def test_odd_paise_rounds_advance_half_up_and_balance_is_remainder(self):
        advance, balance = split_total("100.01")
        self.assertEqual(advance, Decimal("50.01"))
        self.assertEqual(balance, Decimal("50.00"))
        self.assertEqual(advance + balance, Decimal("100.01"))

    def test_whole_paise_total_is_never_lost(self):
        for total in ("0.01", "0.03", "999.99", "12345.67"):
            advance, balance = split_total(total)
            self.assertEqual(advance + balance, Decimal(total))

    def test_invalid_and_negative_amounts_are_rejected(self):
        for value in ("-1.00", "not-money", "NaN", "Infinity"):
            with self.subTest(value=value):
                with self.assertRaises(PaymentLifecycleError):
                    split_total(value)


class CancellationPolicyTests(SimpleTestCase):
    def setUp(self):
        self.ist = ZoneInfo("Asia/Kolkata")
        self.service_time = datetime(2026, 11, 10, 10, 0, tzinfo=self.ist)

    def test_cutoff_is_ten_pm_previous_calendar_day_in_ist(self):
        self.assertEqual(
            cancellation_cutoff(self.service_time),
            datetime(2026, 11, 9, 22, 0, tzinfo=self.ist),
        )

    def test_exact_cutoff_is_refundable(self):
        cutoff = cancellation_cutoff(self.service_time)
        self.assertTrue(customer_cancellation_is_refundable(self.service_time, now=cutoff))

    def test_one_microsecond_after_cutoff_is_not_refundable(self):
        from datetime import timedelta
        cutoff = cancellation_cutoff(self.service_time)
        self.assertFalse(
            customer_cancellation_is_refundable(
                self.service_time, now=cutoff + timedelta(microseconds=1),
            )
        )

    def test_utc_timestamp_is_compared_as_ist_local_time(self):
        from datetime import timezone as dt_timezone
        cutoff_utc = datetime(2026, 11, 9, 16, 30, tzinfo=dt_timezone.utc)
        self.assertTrue(customer_cancellation_is_refundable(self.service_time, now=cutoff_utc))

    def test_naive_datetimes_are_rejected(self):
        with self.assertRaises(PaymentLifecycleError):
            cancellation_cutoff(datetime(2026, 11, 10, 10, 0))


class RefundCalculationTests(SimpleTestCase):
    def test_customer_refund_deducts_one_fixed_fee(self):
        self.assertEqual(calculate_customer_refund("500.00"), Decimal("460.00"))

    def test_customer_refund_never_goes_below_zero(self):
        self.assertEqual(calculate_customer_refund("25.00"), Decimal("0.00"))
        self.assertEqual(calculate_customer_refund("40.00"), Decimal("0.00"))

    def test_platform_inability_refunds_full_collected_amount(self):
        self.assertEqual(calculate_platform_refund("500.25"), Decimal("500.25"))
