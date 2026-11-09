# AIRway Payment and Service Lifecycle Policy

This document is the product and engineering source of truth for the split-payment rollout.

## Customer payment policy
- The customer pays 50% of the server-calculated order total at booking checkout.
- The remaining 50% becomes due only after the service is completed and the completion OTP is verified.
- Calculate the advance from the immutable checkout total (service/variant, selected add-ons, quantity, tax and discounts). Round the advance to INR paise using a documented decimal rounding rule; the balance is the exact remainder so both instalments sum to the frozen total.
- Never accept a client-supplied total or instalment amount as authoritative.
- A booking/order is not eligible for worker dispatch until its advance payment is captured and verified.
- Wallet value, if supported for this checkout, must be allocated explicitly to the advance and must not silently reduce the final balance.

## Customer cancellation
- Cutoff is 10:00 PM (Asia/Kolkata) on the calendar day before the scheduled service date.
- Cancellation at or before the cutoff is eligible for a refund equal to the amount actually collected from the customer for the cancelled booking/order line, less one fixed INR 40 platform fee. Refund cannot be negative.
- Cancellation after the cutoff is not eligible for a customer-initiated refund.
- Once the service-start OTP has been verified and the booking enters in_progress, customer cancellation is blocked. A customer may still raise a support/dispute case; that is not a cancellation and must not trigger an automatic refund.
- The server must evaluate the cutoff using the booking's scheduled time zone (Asia/Kolkata for the initial Rawatbhata launch), not the device clock.
- Refund calculation and refund initiation must be idempotent. The INR 40 deduction applies once per cancelled booking line, never once per payment attempt or webhook.

## Provider / platform inability to fulfil
- If AIRway or the assigned worker cannot fulfil before service starts, do not apply the customer's INR 40 cancellation fee. Refund all customer-collected funds for the affected line.
- If a worker rejects or becomes unavailable, the system should attempt reassignment according to existing dispatch rules before declaring fulfilment failure. Do not bypass existing worker eligibility, priority batches, or atomic parent-order assignment.
- If the platform cancels only one line of a multi-service order, calculate refund and outstanding balance for that line only. Preserve unaffected lines and the parent order's financial ledger.

## Service OTP lifecycle
- Start OTP and completion OTP are distinct, single-use challenges.
- Only the customer may retrieve the active OTP for their own booking. Only the currently assigned worker may submit it.
- OTPs must be stored hashed, expire, have bounded verification attempts, and be rate-limited. Never log or expose an OTP to workers, admins in routine views, analytics, or third-party clients.
- A valid start OTP atomically records started_at and transitions the booking to in_progress. From that point customer cancellation is forbidden.
- A valid completion OTP atomically records completed_at, transitions the booking to completed, and makes the remaining balance payable.
- Replays, expired OTPs, wrong workers, wrong customers, already-consumed OTPs, and invalid booking states must be rejected.
- A service cannot be completed merely by calling a status endpoint without a valid completion OTP.

## Payment ledger and gateway rules
- Represent the booking/order financial plan separately from gateway payment attempts.
- Track advance and final-balance instalments independently, including amount due, amount captured, gateway order/payment IDs, status, timestamps, and reconciliation metadata.
- Keep every gateway attempt and refund auditable. Do not overwrite a prior captured attempt when retrying.
- Treat only Razorpay payment.captured with a matching order ID, payment ID, exact amount and currency as settlement. payment.authorized is not captured.
- Webhooks and checkout verification must be idempotent. Duplicate, delayed and out-of-order events must not double-credit, double-debit, dispatch twice, or issue duplicate refunds.
- A failed advance means no worker dispatch. A failed final-balance attempt leaves the balance outstanding and retryable; it must not undo the completed service.
- Refund requests and refund settlement are separate states. Track provider refund IDs and wait for the provider's terminal processed/failed outcome; a successful refund API response alone is not proof that the customer received funds.

## Parent orders and accounting
- Each order line has its own immutable price snapshot, advance allocation, final balance, cancellation eligibility, refund ledger and service OTP lifecycle.
- Parent-order checkout collects the sum of line advances in one customer-facing checkout when practical, but the backend must preserve per-line allocation for partial cancellation and reconciliation.
- A parent order may be dispatched only when all required line advances are captured and verified. Keep the existing rule that one worker accepts the complete order atomically and is eligible for every line.
- Parent-order status is derived from line and financial states; customer GET endpoints must remain read-only.

## Required tests before release
- Exact 50/50 split including odd paise, tax, discount, add-ons and quantity.
- Advance payment success/failure/retry, final payment success/failure/retry, wallet allocation and zero-value edge cases.
- Authorization is not settlement; captured amount/order/payment/currency mismatch and missing fields are rejected.
- Duplicate and out-of-order webhooks; refund created/processed/failed and duplicate refund events.
- Cancellation immediately before, exactly at, and immediately after 10:00 PM cutoff; timezone/daylight/UTC conversion; scheduled-date changes.
- Refund less INR 40, floor at zero, no fee on platform/worker inability, and exactly-once refund.
- Customer cancellation rejected after start OTP; wrong/expired/replayed OTP; wrong customer/worker; OTP brute-force limits.
- Completion OTP gates final-balance payment; duplicate completion does not create duplicate balance due.
- Multi-line order advance collection, one worker atomic assignment, partial line cancellation, full order cancellation, and line-level refund reconciliation.
- Existing wallet, dispatch, booking, notification, payment and Flutter checkout flows remain regression-tested.