# AIRway Payment, Completion & Settlement Policy

**Status:** Approved product direction; implementation exists in the current codebase and requires continued end-to-end verification  
**Last updated:** 12 November 2026  
**Scope:** Customer orders, all service lines, worker fulfilment, wallet and Razorpay

> This is the canonical payment policy. It supersedes the earlier ₹39 booking-fee proposal in this document's history. Do not implement or display the ₹39 fee as the current AIRway policy.

## 1. Customer payment model

- Collect a configurable **30% advance when the customer places an order**.
- Do not start worker dispatch/assignment until the advance payment is verified as successful.
- Collect the remaining **70% only after all services in the order are completed and completion is verified through the customer OTP flow**.
- The percentage is configurable through `ORDER_ADVANCE_PERCENTAGE`, with a default of 30%; the production launch configuration must be reviewed and fixed to the approved value.
- Show the customer the full order total, advance due now, balance due after verified completion, and any wallet contribution before payment confirmation.
- Never treat a client-side success screen, screenshot, or worker assertion as proof of online payment. Verify through server-side Razorpay signature/webhook/reconciliation.

## 2. Multi-service orders and allocation

- An order may contain multiple service/booking lines.
- Allocate the advance and remaining balance deterministically across service lines, using currency-safe decimal arithmetic and assigning any rounding remainder deterministically so line allocations sum exactly to the order totals.
- Persist the allocation snapshot used for payment and refunds; do not recalculate historical allocations from mutable catalogue prices.
- A partial cancellation must adjust the active order allocation safely without charging or refunding unrelated service lines.
- The balance becomes payable only when every non-cancelled service line has reached the required completed state and the completion OTP verification requirements are satisfied.
- If a service line is cancelled or cannot be fulfilled, apply the documented per-service refund/reconciliation rules and recalculate only the still-active unpaid balance.

## 3. Payment methods and wallet

- Razorpay is the online payment gateway for advance and final-balance collection.
- AIRway Wallet may contribute to an eligible payment where supported. Wallet reservations, captures and releases must be ledger-backed, atomic and idempotent.
- A wallet contribution and Razorpay amount must be displayed separately and must sum to the requested stage amount.
- Never double-debit wallet funds on retries, and never release a reservation more than once.
- Cash-after-service is a separate business capability and must not be silently treated as a verified Razorpay payment. It requires an explicit product decision, a recorded collection event, customer confirmation and admin reconciliation before launch.

## 4. Lifecycle and state integrity

1. Customer confirms the order and pays the 30% advance.
2. Backend verifies the payment; only then may dispatch create worker offers.
3. Worker accepts and fulfils the assigned service lines.
4. Worker records completion; customer verifies completion using the required OTP.
5. Once all active service lines are completed and verified, the backend creates or exposes the remaining 70% balance due.
6. Customer pays the balance through Razorpay (and eligible wallet funds).
7. Backend verifies/reconciles payment and marks the order financially settled.

Operational completion and financial settlement are distinct states. An order may be operationally completed while its balance is still pending, failed, or under reconciliation. Do not mark it financially settled until verified funds cover the outstanding amount.

## 5. Reliability and edge cases

Implementation and tests must cover:

- Duplicate checkout requests and idempotent payment-order creation.
- Razorpay signature verification and webhook signature verification.
- Duplicate, delayed, out-of-order and retried webhooks.
- Payment success where the app closes or loses network connectivity.
- Failed, expired, pending and late-captured payments.
- A late capture after cancellation or after the active order allocation changes.
- Wallet reservation, capture, release and retry idempotency.
- Multi-service advance/balance allocation and rounding.
- Partial cancellation, platform/provider non-fulfilment and per-service refunds.
- Refunds split between wallet and gateway components.
- Completion OTP expiry, incorrect attempts, replay and duplicate completion requests.
- Order state changes racing with payment capture, refund or worker acceptance.
- Admin reconciliation and auditable manual exceptions.

Network calls to Razorpay must not be held inside long-running database transactions. Lock ordering, unique constraints and idempotency keys must protect concurrent requests. A gateway timeout is an unknown outcome until reconciled; it is not proof of failure.

## 6. Cancellation and refunds

- Refund eligibility is evaluated per affected service line and payment stage.
- A customer cancellation must not refund another completed or active service line by accident.
- If AIRway or the provider cannot fulfil a service, refund the affected customer's paid amount or offer a rebooking only with the customer's explicit acceptance.
- Wallet-funded amounts return to the wallet; gateway-funded amounts are refunded through Razorpay and reconciled using gateway references.
- Refund requests and processing must be idempotent, with durable states for processing, pending, processed and failed.
- Failed or ambiguous gateway refunds require reconciliation before another refund request is submitted.
- Cancellation cutoffs, no-show fees, cash collection and any other exception policy require explicit product approval and clear customer disclosure; do not infer a ₹39 fee or invent a penalty.

## 7. Admin controls and auditability

Admin operations must be permission-controlled and auditable. Administrators need visibility into order totals, advance/balance stages, service-line allocations, wallet reservations, gateway references, webhook/reconciliation outcomes, refunds and outstanding balances. Manual corrections must record the actor, reason, timestamp and before/after values.

## 8. Source of truth

The backend is authoritative for:
- The configured advance percentage and calculated amounts.
- Order and service-line payment allocations.
- Payment and refund state transitions.
- Completion OTP verification and eligibility to collect the balance.
- Wallet ledger changes and financial settlement.

Flutter displays backend state and submits user intent; it must never independently decide that an order is paid, completed, refunded or settled.

## 9. Verification status

The repository contains staged order payments, per-service allocation, wallet reservation/release, Razorpay verification/webhook paths, completion OTP and refund handling. These are implementation indicators, not proof that the complete production lifecycle is verified. Continue cross-layer review and run the relevant PostgreSQL-backed tests, Flutter model/widget tests, API integration tests and sandbox gateway tests before claiming production readiness.

**Explicitly superseded:** The previous ₹39 booking-fee proposal and its “payment implementation deferred” instruction are not the current AIRway payment policy.
