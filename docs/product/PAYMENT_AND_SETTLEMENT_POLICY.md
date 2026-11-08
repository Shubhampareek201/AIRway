# AIRway Payment, Booking Fee & Settlement Policy

**Status:** Product decision record — approved direction, implementation deferred  
**Last updated:** 8 November 2026  
**Scope:** All AIRway service categories and fulfilment modes

> This document records the payment decisions discussed for AIRway. It is a planning reference only. Do not treat it as implemented behaviour or begin payment changes from this document until the service-category booking flows have been completed and reviewed.

## 1. Product objective

AIRway should make booking feel trustworthy for first-time customers while protecting professionals and businesses from avoidable no-shows. The payment experience must work consistently across the marketplace rather than creating separate payment systems for home visits, business-location appointments and customer-selected locations.

## 2. Agreed booking-fee direction

- Charge a **₹39 booking fee** at booking time.
- The fee applies across all service categories and all supported fulfilment modes:
  - At Home — professional visits the customer.
  - At Business Location — customer visits a salon, car-wash centre or other listed business.
  - At Customer-Selected Location — where the service and provider support it.
- The customer pays the booking fee online before the booking is confirmed.
- The ₹39 is **credited against the final service bill**. It is not intended to be an additional fee on top of the agreed service price.
- Example only: if the final approved service bill is ₹300, the customer has already paid ₹39 and owes ₹261 after service.
- A rescheduled booking should carry its existing booking-fee credit forward; it should not trigger a second fee merely because the appointment was rescheduled.
- The fee is non-refundable for a customer-caused late cancellation or no-show only where the applicable rule was clearly shown and accepted before payment.
- If AIRway, the business or the professional cannot fulfil the confirmed booking, the customer must be offered a refund or a rebooking that the customer explicitly accepts. Do not retain the fee when the platform/provider fails to deliver.

### Decision still required: how the fee applies to multi-service checkout

AIRway supports a parent order containing multiple booking/service lines. The exact ₹39 charging unit has not yet been decided:

- **Option A — ₹39 per order/appointment:** one fee where multiple services are part of the same combined visit or appointment.
- **Option B — ₹39 per booking/service line:** each separately created booking in the order attracts its own fee.

Recommended for customer simplicity: Option A when the services are genuinely part of one combined appointment/visit. If separate appointments, providers or time slots are created, the product may need to treat them as separate booking units. Final rule must be agreed before implementation; do not silently assume either option.

## 3. Remaining service balance

After the service is completed and the final amount is confirmed:

- Online payment through the configured payment gateway (Razorpay) should be the preferred option.
- Cash after service (COD) should also be supported during launch.
- The final payable amount must show an itemised breakdown: agreed base service price, customer-approved additions, applicable adjustments, ₹39 booking-fee credit and remaining balance.
- A customer must approve any extra work or additional charge before it is added. No surprise charges after the work.
- A booking/order must not be marked financially settled merely because a customer or professional says that an online payment was made. Online settlement requires server-side gateway verification/webhook reconciliation.
- Cash collection must be recorded and reconciled; it must not be treated as a verified online payment.

## 4. Cancellation, no-show and fulfilment failure

The following principles are agreed; exact time thresholds and customer-facing wording remain to be finalised.

| Scenario | Intended treatment |
|---|---|
| Customer cancels before the free-cancellation cutoff | Refund the booking fee under the final published cancellation policy. |
| Customer cancels after the cutoff | Booking fee may be retained if the rule was clearly disclosed and accepted. |
| Customer no-show after the defined grace period | Booking fee may be retained if the no-show process and evidence requirements are satisfied. |
| Professional/business cancels or does not arrive | Refund the booking fee, or offer a customer-approved rebooking. |
| AIRway cannot find an eligible provider or cannot fulfil the booking | Refund, or offer an alternative that the customer explicitly accepts. |
| Customer reschedules under the allowed policy | Carry the existing booking-fee credit forward; do not charge again solely for rescheduling. |
| Payment fails before confirmation | Do not confirm the booking; allow a safe retry and release any temporary slot hold when it expires. |
| Payment succeeds but the app loses connection | Reconcile using the gateway's server-side status/webhook before deciding whether to confirm or retry. |

**Open configuration decisions:** free-cancellation cutoff, no-show grace period, evidence required for a no-show, refund processing expectations, and any category-specific exceptions. These must be admin-configurable where appropriate and displayed clearly to customers before checkout.

## 5. Service completion and final-bill controls

A trustworthy close-out flow should provide an auditable record:

1. Professional/business marks arrival or appointment check-in.
2. Customer verifies the professional/booking using an OTP or another approved verification method.
3. Service start is recorded with a timestamp.
4. The scope and expected amount are visible to the customer before work begins.
5. Any scope change or add-on is presented to the customer and explicitly approved before work proceeds.
6. Professional records service completion and the final itemised amount.
7. Customer is notified and can review the final bill and the ₹39 credit.
8. Customer pays the outstanding balance online or in cash.
9. The payment/collection is recorded and reconciled before the order is considered financially settled.

The system should retain timestamps and relevant status history so that disputes can be investigated. Admin overrides must be permission-controlled and auditable.

## 6. Cash collection and unpaid balances

For cash payments:

- Professional records the cash amount received against the correct booking/order.
- Customer confirms the amount/receipt in the app or through an approved confirmation mechanism such as OTP.
- The system stores the cash collection record separately from gateway transactions.
- Admin can review and reconcile cash collections, provider earnings, AIRway commission and outstanding amounts.
- A professional must not be able to mark an online payment as successful by uploading a screenshot or changing a client-side status.

If a customer refuses or fails to pay after service:

- Professional can report the unpaid amount with supporting details/evidence.
- Customer receives a notification and a fair opportunity to respond or raise a dispute.
- Admin reviews disputed cases and records the resolution.
- Verified outstanding balances may restrict future bookings, subject to a clear appeal and Admin-exception process.
- The product must recognise that allowing payment after service carries residual collection/bad-debt risk; app controls cannot guarantee collection.

## 7. Payment integrity and edge cases

Implementation must account for:

- Idempotency to prevent duplicate booking-fee or balance charges.
- Server-side verification of gateway orders and payments.
- Webhook-based reconciliation when the customer closes the app, loses connectivity or returns late from checkout.
- Safe retry behaviour after payment failure.
- Temporary slot holds with expiry, so failed payment does not block availability indefinitely.
- Refund tracking and clear payment/refund states.
- Partial, duplicate, failed, pending and reversed transactions.
- Multiple booking lines under one parent order, including clear allocation of fee credits and balance payments.
- Atomic, consistent order-level status transitions; payment for one line must not accidentally settle unrelated lines.
- Admin audit history for refunds, cash reconciliation, manual corrections and exceptions.

## 8. Admin controls

Admin should be able to configure and audit, without requiring an app release where practical:

- Booking-fee amount (initial agreed value: ₹39).
- Whether the fee is enabled for a service/category and supported fulfilment mode, while preserving the agreed all-services/all-modes launch default.
- Fee application unit once the multi-service rule is decided.
- Cancellation cutoff and no-show grace period.
- Refund/rebooking handling and reason codes.
- Supported payment methods (online and cash).
- Cash reconciliation, unpaid balances, disputes and controlled exceptions.
- Payment/refund status history and staff actions.

Any change to the ₹39 policy should be versioned and applied transparently to new bookings; existing bookings should retain the policy terms shown at the time of booking.

## 9. Unified payment model

Use one payment and settlement architecture for all fulfilment modes. The booking's fulfilment mode determines where/how the service is delivered; it should not create a separate payment engine.

The model should distinguish at least:

- Booking fee collected.
- Booking-fee credit applied to the final bill.
- Final service amount agreed by the customer.
- Outstanding balance.
- Online payment transaction status.
- Cash collected and confirmation status.
- Refund amount/status.
- Disputed or unpaid balance.
- Financial settlement status.

Booking/order lifecycle status and financial settlement status should be related but distinct. For example, a service can be operationally completed while its balance remains unpaid or disputed.

## 10. Implementation sequence — deliberately deferred

Do not implement the payment flow yet. Complete and validate the full service-category and booking experience first.

When the team returns to payments:

1. Reconfirm the multi-service fee unit and all open policy thresholds.
2. Audit the complete current checkout, booking, dispatch, completion, payment, refund and COD code paths.
3. Design the data model and state transitions before editing code.
4. Implement booking-fee collection and credit allocation.
5. Implement final-bill approval, online balance payment and cash collection/reconciliation.
6. Secure all completion/payment endpoints and remove inconsistent duplicate pathways.
7. Add tests for gateway failures, webhook retries, duplicate requests, cancellations, no-shows, refunds, COD, multi-line orders and disputes.
8. Review customer-facing policy wording and applicable legal/payment requirements before public launch.

## 11. Explicit non-goals for the current phase

- No payment code changes as part of recording this document.
- No assumption that the ₹39 fee is charged per service line until the open decision is resolved.
- No invented service prices, cancellation thresholds, refund timelines or legal claims.
- No treating a customer screenshot or client-side flag as proof of payment.
- No marking an order financially settled while a verified balance remains outstanding.

---

**Decision summary:** ₹39 paid online at booking, credited against the final bill, across all services and fulfilment modes; remaining balance payable after service online (preferred) or cash; customer-caused late cancellation/no-show may forfeit the fee under a clearly disclosed policy; provider/AIRway failure leads to refund or customer-approved rebooking. **Implementation is intentionally postponed until the service-category flows are complete.**
