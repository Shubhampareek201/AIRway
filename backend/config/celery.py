"""
Celery configuration for AIRway project.
"""
import os
from celery import Celery
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('airway')

app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'expire-pending-offers-every-minute': {
        'task': 'apps.bookings.tasks.expire_pending_offers',
        'schedule': 60.0,
    },
    'retry-failed-dispatches-every-minute': {
        'task': 'apps.bookings.tasks.retry_failed_dispatches',
        'schedule': 60.0,
    },
    'timeout-pending-payments-every-minute': {
        'task': 'apps.bookings.tasks.timeout_pending_payments',
        'schedule': 60.0,
    },
    'expire-unpaid-checkouts-every-minute': {
        'task': 'apps.bookings.tasks.expire_unpaid_checkouts',
        'schedule': 60.0,
    },
    'setup-recurring-wash-visits-every-five-minutes': {
        'task': 'apps.bookings.tasks.setup_recurring_wash_visit_bookings',
        'schedule': 300.0,
    },
    'dispatch-due-recurring-wash-visits-every-minute': {
        'task': 'apps.bookings.tasks.dispatch_due_recurring_wash_visits',
        'schedule': 60.0,
    },
    'expire-past-worker-leave-requests-every-hour': {
        'task': 'apps.workers.tasks.expire_past_worker_leave_requests',
        'schedule': 3600.0,
    },
    'expire-past-rework-proposals-every-minute': {
        'task': 'apps.bookings.tasks.expire_past_rework_proposals',
        'schedule': 60.0,
    },
}