# AIRway recurring Car Wash operations

Recurring visits require three independent processes: Django, Redis, and Celery worker/Beat. The booking API and database alone do not execute the scheduled setup or dispatch jobs.

## Local Windows development

Start Postgres and Redis using the existing backend Compose file:

```powershell
cd backend
docker compose up -d db redis
```

In the first PowerShell terminal, from `backend` with the project virtual environment activated:

```powershell
python manage.py check
python -m celery -A config worker --loglevel=INFO --pool=solo
```

In a second PowerShell terminal:

```powershell
cd C:\Users\shubh\Desktop\AIRway\backend
.venv\Scripts\Activate.ps1
python -m celery -A config beat --loglevel=INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

Keep both processes running. Start Django separately as usual.

## Verify the processes

- Redis responds: `redis-cli ping` should return `PONG`.
- Worker responds: `python -m celery -A config inspect ping` should return a pong from at least one worker.
- Beat is alive: its console should continue running and log the due recurring tasks. Look for:
  - `setup-recurring-wash-visits-every-five-minutes`
  - `dispatch-due-recurring-wash-visits-every-minute`
- A task execution should log the number of bookings created or worker offers dispatched. A task returning zero is valid when no visits are due.

## Recurring visit operations

- Paid visit rows that cannot be booked remain `pending_setup`; the setup task retries every five minutes.
- Admin can correct a pending visit's `scheduled_at` and notes in the Recurring Wash Plan inline, then use **Retry setup for pending recurring visits**.
- Due visits are offered to eligible workers during the 24 hours before their scheduled time.
- Customer cancellation closes undelivered visits and triggers a refund of their unused prepaid allocation. Completed and in-progress visits are excluded.
- Refunds with an uncertain Razorpay result remain non-retryable until reconciled; do not issue a second refund manually without checking Razorpay first.

## Deployment requirement

Run one Celery worker service and one Celery Beat service alongside the deployed Django app and Redis. Do not run Beat as multiple replicas; duplicate Beat instances can enqueue duplicate scheduled work. The repository's current `backend/docker-compose.yml` starts only Postgres and Redis, so it does not prove that worker or Beat is running in any deployed environment.
