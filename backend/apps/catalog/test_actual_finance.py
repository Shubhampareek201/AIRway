from decimal import Decimal
from types import SimpleNamespace
from django.test import SimpleTestCase
from apps.catalog.actual_finance import _booking_payment_allocation, _money

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