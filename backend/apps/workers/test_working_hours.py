from datetime import datetime, time

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.workers.eligibility import worker_is_within_working_hours
from apps.workers.models import WorkerProfile, WorkerSchedule


class WorkerCurrentWorkingHoursTests(TestCase):
    def test_current_shift_uses_local_weekday_and_half_open_time_window(self):
        user = User.objects.create_user(
            phone="+919876543280", password="password123", name="Shift Worker"
        )
        worker = WorkerProfile.objects.create(
            user=user, status=WorkerProfile.Status.APPROVED, is_online=True
        )
        with timezone.override("Asia/Kolkata"):
            WorkerSchedule.objects.create(
                worker=worker,
                weekday=5,
                start_time=time(9, 0),
                end_time=time(18, 0),
                is_active=True,
            )
            inside = timezone.make_aware(datetime(2026, 11, 28, 10, 0))
            at_end = timezone.make_aware(datetime(2026, 11, 28, 18, 0))
            other_day = timezone.make_aware(datetime(2026, 11, 29, 10, 0))

            self.assertTrue(worker_is_within_working_hours(worker, at=inside))
            self.assertFalse(worker_is_within_working_hours(worker, at=at_end))
            self.assertFalse(worker_is_within_working_hours(worker, at=other_day))
