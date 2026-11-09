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
    'reconcile-unresolved-refunds-every-five-minutes': {
        'task': 'apps.payments.tasks.reconcile_unresolved_refunds',
        'schedule': 300.0,
        'kwargs': {'batch_size': 100},
    },
}