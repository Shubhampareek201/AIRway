# AIRway Split-Payment Implementation Plan

Status: engineering plan; no runtime behavior is changed by this document.

## Current baseline

- Implementation starts from `fix/order-read-state-integrity` at `54db46f6e2d8426a677ce09c94ad9cf7556f3212`.
- The existing Payment row is one-to-one with a booking or parent order and combines financial state with Razorpay attempt identifiers. It cannot safely represent two instalments, multiple attempts, per-line allocations, or multiple refunds.
- Existing parent-order dispatch is initiated before payment and worker acceptance currently creates/opens payment afterward. The approved advance-before-dispatch policy therefore changes the booking/order state machine and must be implemented as a coordinated flow, not as a payment percentage patch.
- Existing local worktree changes are outside this branch and must remain untouched.

## Target domain model

Implement additive, backward-compatible ledger entities before switching checkout behavior:

1. **BookingFinancialPlan** (one-to-one per booking line): immutable currency and gross total snapshot; advance due; final balance due; amounts captured/refunded; platform cancellation fee; calculation version and timestamps. Amounts use Decimal(10,2), never float.
2. **PaymentInstallment** (per booking line and installment kind): ADVANCE or FINAL_BALANCE; due/captured amounts; state; due/settled timestamps. Unique constraint per booking and kind.
3. **PaymentAttempt** (per installment): immutable gateway order/payment IDs, provider, amount in paise, currency, attempt state, capture metadata and idempotency key. Never reuse or overwrite a captured attempt.
4. **RefundRecord** (per cancelled line and source capture): amount, fixed fee allocation, reason, provider refund ID, request state and terminal settlement state. Unique idempotency key prevents repeated refunds.
5. **ServiceOTPChallenge** (per booking and START/COMPLETION): keyed hash, expiry, attempt count, consumed timestamp, generated timestamp and delivery metadata. Never persist plaintext OTP.

For parent orders, keep each booking line as the financial accounting unit. Aggregate advance collection can be supported by a checkout batch/payment order, but every captured paise must be allocated back to line-level advance installments transactionally. Do not use a single parent-order total as the only ledger.

## State-machine and workflow changes

### Checkout and dispatch
- Freeze server-calculated price snapshot at booking/order creation.
- Create line-level 50/50 financial plans. Advance = gross total / 2 rounded to paise with an explicit ROUND_HALF_UP policy; final balance = gross total - advance.
- Place new bookings/orders into a payment-gated state. Do not create worker offers until every required line advance is captured and reconciled.
- On captured advance, atomically mark advance installments settled and enqueue dispatch after transaction commit. Keep existing worker eligibility, priority batches and atomic same-worker parent-order assignment.
- Payment authorization, checkout callback, or client-side success alone never triggers dispatch.
- Existing pre-rollout bookings/payments must retain their legacy behavior. Add an explicit legacy/plan version discriminator; do not infer old records as 50/50.

### Service execution
- Customer retrieves start/completion OTP only for their own booking and only in the expected state.
- Only the currently assigned worker can submit the corresponding OTP.
- Hash OTP at rest; use constant-time comparison; enforce expiry, bounded attempts and throttling.
- Start verification and the IN_PROGRESS transition occur under one row lock and transaction. Once started, cancellation is forbidden.
- Completion verification, COMPLETED transition, and final-balance due creation occur under one row lock and transaction. Status-only APIs cannot bypass either transition.
- Repeated OTP submissions are rejected without repeating side effects.

### Cancellation and refunds
- Enforce cutoff server-side in Asia/Kolkata: 10:00 PM on the calendar day before scheduled service; exactly 10:00 PM remains eligible.
- Reject customer cancellation after start OTP.
- Before/at cutoff, refund collected customer funds for the affected line less one ₹40 fee, floored at zero. After cutoff, no customer-initiated refund.
- Platform/worker inability before service start produces full refund with no ₹40 fee.
- Refund request and provider refund settlement are separate states; wait for provider terminal events.
- Parent-order line cancellation must not affect other lines. Parent-order cancellation policy and existing API guardrails must be reconciled before enabling any line-cancel endpoint.

### Gateway and wallet integrity
- Require exact order ID, payment ID, captured status, amount in paise and INR currency on webhook and checkout verification.
- Missing amount/currency/identifiers are rejected; use Decimal-to-paise conversion, not float.
- Wallet reservations/credits must be allocated to the correct installment and reversed exactly once on failure/refund.
- Persist raw provider references safely without secrets or OTPs.
- Handle duplicate, delayed and out-of-order capture/refund events idempotently.

## Delivery sequence

1. **Schema and ledger foundation**: additive models, constraints, migrations, admin read-only/audit views, model/service tests. No checkout behavior switch.
2. **Capture hardening**: finish Razorpay webhook and checkout verification strictness, including wallet top-ups and missing-field tests.
3. **Single-booking advance flow**: create financial plan, collect advance, capture gate, then dispatch. Keep legacy records untouched.
4. **Parent-order advance flow**: aggregate checkout with exact line allocations; preserve atomic one-worker assignment.
5. **OTP service lifecycle**: customer OTP retrieval, worker verification endpoints, expiry/attempt throttling, start/completion atomicity.
6. **Cancellation/refund ledger**: cutoff, fee allocation, platform exception, provider refund reconciliation, parent-line accounting.
7. **Flutter integration**: update API models/repositories, customer checkout and payment status, booking details/OTP surfaces, worker start/complete flow, balance payment and refund status.
8. **Release hardening**: full backend and Flutter regression, migration dry-run, concurrency/idempotency tests, staging Razorpay test mode, rollback/feature-flag plan.

## Non-negotiable regression gates

- Existing bookings, orders, wallet top-ups, wallet reservations, dispatch eligibility, offer expiry, notifications and customer read-only GET semantics remain intact.
- A parent order is never partially assigned to different workers.
- No worker offer exists before all required advances are captured.
- A final-balance failure never rolls back a completed service.
- No client amount, status, timestamp, or device clock is authoritative.
- No migration rewrites historical payment rows into the new ledger without a reviewed data migration and reconciliation.
- Do not enable the new flow until backend and Flutter contracts are deployed compatibly.

## Test matrix

Include unit, API, concurrency and integration coverage for:
- Decimal split, odd paise, discounts, tax, quantity, add-ons and price mutation after booking.
- Duplicate checkout requests and concurrent advance capture.
- Authorization vs capture, wrong/missing order/payment IDs, amount/currency mismatch, duplicate/out-of-order webhooks and gateway fetch failures.
- Wallet-only, wallet-plus-gateway, failed reservation, failed capture, reversal and duplicate wallet events.
- Parent-order collection and line allocation, partial line cancellation, unaffected line balances, and atomic worker assignment.
- OTP wrong actor, wrong code, expiry, replay, max attempts, concurrent submissions, status bypass and duplicate completion.
- Cancellation immediately before, exactly at and immediately after cutoff; UTC/Asia-Kolkata boundary; scheduled-time changes.
- ₹40 fee exactly once, zero-floor refund, platform-caused full refund and provider refund pending/processed/failed.
- Full backend and Flutter regression suites plus migration checks.

## Rollout safety

- Feature-flag the new payment lifecycle; default off until migration, backend, Flutter and staging verification are complete.
- New financial plans are created only for new bookings after activation.
- Keep legacy payment/booking paths readable and operable during rollout.
- Add reconciliation reports for captured amounts, line allocations, outstanding balances and refunds before launch.
- Do not merge or activate the feature based only on unit tests; require end-to-end Razorpay test-mode evidence.
