"""
Celery tasks for payment processing.
This module is kept for future payment-specific tasks.
Currently, payment timeout handling is done in apps.bookings.tasks.
"""
import logging

logger = logging.getLogger(__name__)