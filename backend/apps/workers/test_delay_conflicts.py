from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.utils import timezone

from apps.workers.delay_conflicts import notify_upcoming_booking_conflicts


class WorkerDelayConflictTests(SimpleTestCase):
    def setUp(self):
        self.now = timezone.now()
        self.worker = SimpleNamespace(pk=41)
        self.customer = SimpleNamespace(pk=82)
        self.current = SimpleNamespace(pk=100, appointment_group_id=None)
        self.upcoming = SimpleNamespace(
            pk=200, appointment_group_id=None, customer=self.customer,
        )
        self.assignment = SimpleNamespace(booking=self.upcoming)

    @patch("apps.workers.delay_conflicts.Notification.objects.create")
    @patch("apps.workers.delay_conflicts.Notification.objects.filter")
    @patch("apps.workers.delay_conflicts.BookingAssignment.objects.filter")
    @patch("apps.bookings.dispatcher.DispatcherService._assigned_booking_intervals")
    def test_late_start_notifies_customer_when_expected_finish_overlaps(
        self, intervals, assignments, existing, create_notice,
    ):
        planned_start = self.now - timedelta(minutes=20)
        intervals.side_effect = [
            [(planned_start, planned_start + timedelta(hours=1))],
            [(self.now + timedelta(minutes=25), self.now + timedelta(hours=2))],
        ]
        assignments.return_value.select_related.return_value = [self.assignment]
        existing.return_value.exists.return_value = False

        count = notify_upcoming_booking_conflicts(
            worker=self.worker, current_booking=self.current, now=self.now,
        )

        self.assertEqual(count, 1)
        create_notice.assert_called_once()
        payload = create_notice.call_args.kwargs["data"]
        self.assertEqual(payload["booking_id"], self.upcoming.pk)
        self.assertEqual(payload["estimated_delay_minutes"], 20)
        self.assertEqual(payload["conflict_type"], "late_previous_job")

    @patch("apps.workers.delay_conflicts.Notification.objects.create")
    @patch("apps.workers.delay_conflicts.BookingAssignment.objects.filter")
    @patch("apps.bookings.dispatcher.DispatcherService._assigned_booking_intervals")
    def test_on_time_start_does_not_send_delay_notification(
        self, intervals, assignments, create_notice,
    ):
        intervals.return_value = [(self.now, self.now + timedelta(hours=1))]
        count = notify_upcoming_booking_conflicts(
            worker=self.worker, current_booking=self.current, now=self.now,
        )
        self.assertEqual(count, 0)
        assignments.assert_not_called()
        create_notice.assert_not_called()
