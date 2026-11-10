# AIRway Booking and Payment Scenario Matrix

Status: Product/engineering specification for review. This document expands the split-payment foundation into realistic booking, fulfilment, payment, cancellation, refund, and exception scenarios. It does not activate any runtime behavior.

## 1. Goals and non-negotiable invariants

AIRway must support scheduled and urgent service bookings without weakening pricing, payment, worker eligibility, OTP, or accounting integrity.

Confirmed product rules:
- Customer pays 50% of the server-calculated booking-line total before worker dispatch.
- Remaining 50% becomes due only after completion OTP succeeds.
- Customer cancellation is refundable when made at or before 10:00 PM Asia/Kolkata on the calendar day before the scheduled service date: refund captured customer funds less one ₹40 fee per cancelled booking line, floored at zero.
- Customer cancellation after the start OTP is rejected. Support/dispute remains available but is not cancellation.
- Platform/worker inability to fulfil before service start receives a full refund of captured customer funds, without the ₹40 fee.
- Service start and completion require distinct, single-use OTP challenges.
- Parent-order assignment remains all-or-nothing to one eligible worker; existing priority batches and eligibility are not bypassed.
- Historical bookings/payments remain on the legacy lifecycle unless explicitly migrated and reconciled.

System invariants:
1. Server-calculated price and persisted price snapshot are authoritative. Client totals, device time, client status, and client payment-success flags are never trusted.
2. No worker offer/dispatch before all required advances for the booking or parent order are captured and allocated.
3. A payment authorization is not a capture. Only verified captured funds settle an installment.
4. Each booking line is the accounting unit, including in a multi-line parent order.
5. A completed service is never reverted because final-balance collection fails.
6. Refund requested is not refund processed. Provider settlement must be reconciled.
7. Duplicate requests, webhooks, retries, and worker actions must be idempotent.
8. No worker can start or complete a service for a booking not assigned to that worker.
9. No cancellation after start OTP; a dispute/support case is a separate workflow.
10. Do not silently reprice a confirmed booking. Any customer-approved change creates a versioned price adjustment with an auditable reason.

## 2. Booking intent and scheduling scenarios

### 2.1 Standard scheduled booking
Flow: customer chooses service and a future slot -> backend validates slot and service area -> final price snapshot -> create line financial plan -> collect 50% -> verify capture -> dispatch -> worker accepts -> start OTP -> service -> completion OTP -> collect remaining 50%.

Rules:
- Slot availability must be checked by the backend at booking creation and rechecked before dispatch/assignment.
- The selected appointment date/time is distinct from any event date entered in service questions.
- Store timestamps timezone-aware; evaluate cancellation cutoff using Asia/Kolkata local calendar date.

### 2.2 Same-day scheduled booking
Flow: customer chooses a time later today -> backend validates same-day capacity and minimum lead time -> display exact expected slot/window and price -> customer pays 50% -> capture -> dispatch with remaining-time constraints.

Rules:
- Same-day is a scheduling classification, not permission to skip availability, payment, worker eligibility, or OTP.
- Reject a slot if the service duration, travel/buffer, worker schedule, or configured minimum lead time cannot fit.
- Do not promise “ASAP” unless the backend can return a real fulfilment window.
- Same-day cancellation is governed by worker acceptance, not the previous-day 10 PM cutoff: before any worker accepts, the customer receives a full refund of the captured advance; after a worker accepts, customer cancellation is non-refundable.
- The worker acceptance timestamp is the authoritative boundary. Merely sending an offer or assigning a worker internally without a successful acceptance must not trigger the non-refundable rule.
- Once the start OTP is verified, cancellation is blocked; the customer may raise a support/dispute case instead.
- If AIRway or the worker cannot fulfil the service, this is a platform/provider failure rather than customer cancellation and the captured amount is refunded in full, even if the same-day worker-acceptance boundary had been crossed.
- Same-day bookings must still pass backend slot, lead-time, capacity, travel/buffer, and worker eligibility checks. No urgent surcharge or guaranteed arrival SLA is implied by this cancellation policy.

### 2.3 Urgent / ASAP booking
Flow: customer selects Urgent -> backend checks live eligible capacity and service-specific urgent eligibility -> backend returns a concrete arrival window and any configured disclosed urgent fee -> customer confirms final amount -> 50% captured -> dispatch using existing eligibility and priority rules, with urgency used only as a scheduling signal if supported.

Rules:
- Urgent does not mean bypassing dispatch priority batches, worker qualification, zone, gender preference, schedule conflicts, or parent-order atomic assignment.
- If no worker can meet the returned window, do not accept payment as a confirmed urgent booking. Return unavailable or offer the next available slot.
- No hidden surge/urgent fee. Fee must be admin-configured, visible before payment, included in the immutable total, and versioned. Until that exists, urgent fee = zero.
- No hard-coded universal arrival SLA. Store service/zone-specific configurable lead time and promise window; do not label an estimate as a guarantee.
- If urgent service cannot be fulfilled after capture and before start, platform cancellation means full refund.

### 2.4 Future-date / event-date booking
- Event date is an answer/requirement, not the service appointment slot.
- Validate that the selected appointment date satisfies any service-specific event lead-time requirement.
- Rescheduling appointment must recalculate availability and cancellation deadline. Event date remains unchanged unless customer edits it.
- Price changes after rescheduling require explicit customer acceptance before collecting any difference.

### 2.5 Fulfilment modes
- At Home, At Business Location, and Customer-Selected Location use the same payment/OTP ledger.
- Validate location/mode support for the selected service and zone before payment.
- For business-location bookings, store the selected business address and opening/operating window; do not require a home address by assumption.
- For customer-selected location, validate service coverage and worker travel eligibility.
- If location changes after payment, revalidate coverage, worker eligibility, slot, and any price difference before committing the change.

### 2.6 Multi-service parent order
- Every line gets its own immutable price snapshot, financial plan, advance/balance installments, cancellation state, OTP lifecycle, and refund allocation.
- One aggregate checkout may collect the sum of line advances, but capture allocation must be exact and transactional per line.
- Dispatch only after the entire required aggregate advance is captured and all line allocations reconcile.
- Preserve one worker for all lines and existing schedule compatibility checks.
- If one line becomes invalid before dispatch, do not partially dispatch the rest without an explicit supported order-edit flow.
- Partial line cancellation after booking must leave other lines, their balances, assignments, and refunds untouched.
- Parent-order cancellation needs an explicit endpoint/policy; never simulate it by looping unprotected line cancellations.

## 3. Pricing and payment scenarios

### 3.1 Price composition
The server calculates line total from base service/package, quantity, selected add-ons, applicable taxes, discounts/coupons, and any explicitly configured fee. Freeze a complete snapshot with currency, calculation version, line components, and total. Advance is 50% rounded HALF_UP to paise; balance is exact remainder.

Test zero/very-low/odd-paise totals, discounts greater than allowed, add-on changes, quantity changes, tax changes, stale catalogue price, inactive package, and currency mismatch. Reject invalid totals; never accept a client-supplied amount.

### 3.2 Advance payment
- Advance is due at checkout before dispatch.
- Razorpay order creation failure: keep booking in payment-required state; no dispatch.
- Customer closes checkout: payment remains pending; allow safe retry with a new immutable attempt or reuse only a still-valid matching attempt according to gateway rules.
- Authorization without capture: remain unpaid; no dispatch.
- Captured event: verify exact provider order ID, payment ID, amount in paise, currency, and captured status; settle once.
- Duplicate capture/webhook: no duplicate allocation or dispatch.
- Wrong order/payment/amount/currency, missing required fields, or unknown attempt: quarantine/reject and reconcile; never mark paid.
- Delayed capture after customer abandons checkout: if booking still valid, reconcile and proceed; if booking expired/cancelled/slot no longer viable, refund captured funds in full and do not dispatch.
- Concurrent capture callbacks: lock payment attempt/installment/order and use unique idempotency constraints.
- Partial/mismatched capture: do not dispatch; place in reconciliation state and refund or resolve through support.
- Payment gateway outage: retain payment-required state and allow retry; do not create duplicate booking/order on retry.

### 3.3 Wallet and mixed tender
- If wallet is offered, reserve wallet amount against the exact advance due, not the full booking total.
- Wallet-only advance: after atomic wallet debit/reservation is confirmed, mark advance captured/settled and dispatch.
- Wallet + Razorpay: line allocations identify both sources; dispatch only when the combined required advance is fully covered.
- Razorpay failure after wallet reservation: release reservation exactly once.
- Duplicate wallet debit/reversal event: idempotent ledger entry prevents double movement.
- Cancellation/refund: refund gateway and wallet portions to their original sources unless an explicit compliant policy says otherwise; never refund more than captured from each source.
- If wallet is disabled or unavailable, do not let the payment code assume it exists.

### 3.4 Final balance after service
- Completion OTP succeeds -> service becomes completed and final balance becomes due.
- Try configured payment method only with customer consent and supported saved-payment mandate; otherwise show pay-now checkout.
- Customer exits/declines/fails final payment: service remains completed, balance remains outstanding, retries are allowed, and no second service completion is created.
- Duplicate final payment callback settles only once.
- Customer pays partially (only if partial payment is deliberately supported): record partial amount and outstanding remainder; do not mark fully paid.
- Final payment authorization without capture remains outstanding.
- Never generate another advance after completion.
- Outstanding balance requires customer-visible amount, due status, payment history, retry action, and support path. Collection/escalation policy needs separate approval; do not invent late fees or auto-debit.

### 3.5 Price changes, extras, and scope changes
- Before payment: update server quote and show revised total before checkout.
- After advance but before start: require a change request with reason, itemized delta, customer acceptance, and an additional payment/credit ledger entry. Never mutate original financial snapshot.
- During service: worker cannot add charges unilaterally. Customer must approve an itemized change in-app before work outside original scope begins.
- If customer rejects extra work, complete original scope and retain original balance.
- Refund/discount after capture must be a separate credit/refund record, not destructive editing of captured payment.
- Out-of-scope work, damaged property, or disputed quality goes to support/dispute workflow.

## 4. Worker dispatch and fulfilment scenarios

### 4.1 No eligible worker before dispatch
- Do not send offers if advance is not fully captured.
- If no eligible worker for selected slot, offer a real alternative slot or cancel the order with full refund if funds were already captured.
- Do not relax worker approval, service capability, zone, schedule, leave, gender preference, or conflict rules to force a match.

### 4.2 Offers expire, decline, withdraw, or no response
- Continue existing priority batches and configured expiry.
- Never create duplicate active offers for the same booking/worker.
- After all batches are exhausted, mark fulfilment unavailable and trigger platform full-refund workflow for captured funds.
- Parent-order offer acceptance/rejection remains atomic across all lines.

### 4.3 Worker accepts then cancels / becomes unavailable
- Before start OTP: attempt reassignment using existing eligibility/priority rules and preserve original slot only if still feasible.
- If reassignment cannot meet the promised window, inform customer and offer reschedule or full platform refund.
- Do not charge the customer a cancellation fee for platform/worker failure.
- After start OTP: worker cannot mark cancelled as an ordinary cancellation; create incident/support case and preserve evidence/status.

### 4.4 Worker late / customer unavailable
- Record arrival/check-in timestamp and customer contact attempts; do not use worker-entered timestamps as authoritative without server receipt and audit.
- Define configurable grace periods and no-show outcomes before launch; they are currently policy decisions, not assumed values.
- If customer unavailable, worker must use an explicit “customer unavailable” workflow with evidence and support review; do not automatically mark completed or collect final balance.
- If worker no-show, treat as platform fulfilment failure and full refund before start.
- If delay makes the slot impossible, customer chooses wait/reschedule/cancel; disclose any consequences before confirmation.

### 4.5 Service start and completion OTP
- Start OTP may be issued only to the authenticated booking customer when booking is assigned and advance is fully captured.
- Only the currently assigned worker may submit start OTP.
- Successful start OTP atomically consumes challenge and transitions to IN_PROGRESS; customer cancellation is then rejected.
- Completion OTP may be issued only while IN_PROGRESS.
- Successful completion OTP atomically consumes challenge, marks COMPLETED, and makes final balance due.
- OTP is hashed at rest, short-lived, single-use, bounded attempts, rate-limited, and never logged.
- Wrong actor, wrong code, expired code, replay, max attempts, simultaneous submissions, changed assignment, and status bypass must be tested.
- OTP delivery failure: do not expose plaintext to worker or logs; allow throttled reissue to customer through an approved delivery channel.
- Lost phone/no network: support-assisted identity verification is a separate audited exception; support must not fabricate an OTP or silently bypass the milestone.
- For a multi-line order, OTPs remain per booking line unless the product explicitly defines a grouped milestone; no implicit shared OTP.

## 5. Cancellation, reschedule, and refund scenarios

### 5.1 Customer cancellation before cutoff
- Server compares current Asia/Kolkata time with 10 PM on the calendar day before scheduled service.
- At exactly 10:00 PM is eligible.
- Refund = captured customer funds allocated to the cancelled line minus one ₹40 fee, floor zero.
- If nothing was captured, no gateway refund is created; release any wallet reservation.
- If captured amount is ₹40 or less, refund amount is zero and the fee cannot exceed captured funds.
- Fee is charged once per cancelled line, not per payment attempt, webhook, or refund retry.

### 5.2 Customer cancellation after cutoff but before start
- Under the confirmed policy, no customer-initiated refund.
- Cancellation request is still recorded with timestamp/reason and line status; do not imply payment refund.
- If service is rescheduled by mutual agreement or exceptional support, use a separate audited adjustment; do not silently rewrite the original cutoff.

### 5.3 Same-day urgent cancellation
- The standard previous-day cutoff is already passed. This policy conflict is called out in section 2.2.
- Do not implement a guessed grace period. Obtain explicit product approval for strict non-refundable same-day booking versus a short grace window before worker acceptance.

### 5.4 Cancellation after start OTP
- Reject cancellation endpoint with conflict response.
- Customer can raise a service issue/dispute/support request.
- Do not auto-refund or reverse final balance merely because a dispute was opened.
- Support resolution creates explicit adjustment/refund records with reason, actor, evidence, and audit trail.

### 5.5 Platform/worker cancellation before start
- Full refund of all captured customer funds for affected line, no ₹40 fee, regardless of customer cutoff.
- Release wallet reservations and stop/expire outstanding offers.
- Parent order: only affected lines can be refunded if remaining lines can still be fulfilled consistently; otherwise cancel whole order and refund every affected line. Do not partially assign.
- Customer receives status updates and refund reference; final refund state updates only after provider confirmation.

### 5.6 Refund provider lifecycle
- Create refund request idempotently per source capture and cancellation reason.
- Store requested, pending, processed, failed; provider refund ID must be unique.
- API acceptance is not proof of money returned.
- Retry only when provider state permits; do not create a second refund while first is pending.
- On processed event, reconcile amount and source payment; on failure, alert support and expose retry/escalation.
- Duplicate/out-of-order refund events must not double-credit wallet or reduce ledger twice.
- Partial refund must preserve remaining captured/settled amount and line balance accurately.

### 5.7 Reschedule
- Before start only; lock booking/order while changing slot.
- Revalidate service active, zone, address/mode, capacity, worker availability, and parent-order schedule compatibility.
- If worker already assigned, require worker acceptance of new slot or perform controlled reassignment.
- Recompute cancellation cutoff from the new scheduled service date and retain previous schedule history.
- Keep price unchanged unless the new slot has a disclosed configured price difference; customer must accept any increase before payment.
- After start OTP, rescheduling is not ordinary rescheduling; use support/dispute.

### 5.8 Partial cancellation in a parent order
- Cancel only the selected eligible booking line.
- Refund and ₹40 fee are calculated only against that line's captured allocation.
- Other lines keep their financial plans, captured advance, worker assignment, completion OTP, and final balance.
- Recalculate parent aggregate display totals from line ledgers; never rewrite historic gross snapshots.
- If all lines are cancelled, parent order becomes cancelled; if some remain, partially-cancelled; if all remaining lines complete, final parent status reflects completion/payment aggregation.

## 6. Failure, safety, and operational scenarios

- Customer double taps booking/payment: idempotency key and uniqueness prevent duplicate order, financial plan, and provider order.
- Client app killed during checkout: fetch server payment/booking state on reopen; never infer failure or success from local state.
- Network lost after Razorpay success: webhook reconciliation settles capture; client polling is read-only.
- Webhook delayed or unavailable: scheduled reconciliation fetches provider state; dispatch waits for verified capture.
- Webhook arrives before local callback: same idempotent settlement path.
- Payment captured after cancellation/expiry: full refund/reconciliation; no dispatch.
- Database transaction fails after gateway capture: webhook retry/reconciliation repairs ledger; unique provider IDs prevent duplicate allocation.
- Celery task retried: dispatch task idempotent and checks current order/advance state under lock.
- Notification/SMS fails: booking/payment state remains authoritative; retry notification independently.
- Worker app offline: offer expiry and reassignment continue server-side; no fake acceptance.
- Customer account deleted/deactivated: preserve financial/audit records under retention policy; block new booking as appropriate.
- Worker account suspended after acceptance: prevent start; reassign or platform-cancel/refund before start.
- Service/category/zone disabled after booking: existing paid booking is honoured only if fulfilment remains safe/valid; otherwise platform-cancel/full-refund. Do not make customer bear fee.
- Address invalid or inaccessible: support workflow; do not mark completed without completion OTP.
- Clock/timezone/DST boundary: Asia/Kolkata server time, aware timestamps, tests at day boundary and UTC conversion.
- Admin manual adjustment: permission-restricted, reason required, before/after values audited, never edit captured provider IDs or delete ledger entries.
- Data reconciliation mismatch: quarantine for support; never auto-dispatch or auto-complete.
- App/API version skew: old clients cannot trigger new flow incorrectly; versioned response contract and feature flag keep rollout safe.

## 7. State-machine proposal

Booking lifecycle (new split-payment cohort):
- PAYMENT_REQUIRED -> PAYMENT_RECONCILIATION (optional exceptional state) -> AWAITING_ASSIGNMENT -> ASSIGNED -> IN_PROGRESS -> COMPLETED.
- Before start, cancellation can transition to CANCELLED subject to refund policy; platform inability transitions to PLATFORM_CANCELLED/fulfilment-failed outcome.
- Do not overload payment status as booking status.
- Keep payment lifecycle independent: ADVANCE_DUE -> ADVANCE_PENDING -> ADVANCE_PAID; FINAL_NOT_DUE -> FINAL_DUE -> FINAL_PENDING -> FINAL_PAID; refunds tracked separately.
- Exact enum names must be reconciled with current model choices before migrations. Avoid adding overlapping states if existing fields can safely express the state.

Order lifecycle:
- PAYMENT_REQUIRED -> PAYMENT_RECONCILIATION (if needed) -> AWAITING_ASSIGNMENT -> AWAITING_SERVICE / PARTIALLY_CANCELLED -> COMPLETED / CANCELLED.
- Existing Order.Status values are currently AWAITING_ASSIGNMENT, AWAITING_PAYMENT, PAID, PARTIALLY_CANCELLED, CANCELLED. Do not repurpose these without reviewing every serializer, view, admin, task, and Flutter consumer.
- Parent order aggregate payment status is derived from line installments and allocations, not a substitute for per-line ledger.

## 8. Data and API design implications

Before implementation, inspect and map:
- Booking, Order, OrderItem, Payment, wallet models and all existing status transitions.
- Booking creation/cart checkout, price calculation, order payment endpoint, Razorpay webhooks/checkout verification, wallet reservation and reversal.
- Dispatcher entry points, offer expiry/decline/withdraw, assignment acceptance, parent-order atomic assignment.
- Customer cancellation, parent-order cancellation, worker rejection/cancellation, reschedule, admin actions.
- OTP customer endpoint, worker start/complete endpoints, service status mutation endpoints.
- Flutter API clients, DTOs, checkout screens, booking/order detail, worker offers/job detail, start/complete UI, payment/refund state display.
- Notifications, Celery retries, scheduled reconciliation, audit logs, support/admin workflows.

API contract should expose server-derived:
- booking/order lifecycle state;
- line-level gross, advance due/paid, final balance due/paid, refund status/amount;
- slot/urgent eligibility and explicit fulfilment window;
- allowed actions for current actor;
- cancellation eligibility and reason (not only a boolean);
- reschedule eligibility;
- payment attempt state and safe provider references, never secrets or OTP hashes.

Use versioned serializers/feature flags so legacy clients and historical records remain compatible.

## 9. Implementation phases and exit gates

1. **Scenario/policy sign-off**: resolve same-day cancellation treatment, urgent promise/lead-time configuration, grace periods/no-show rules, and any urgent fee. No guessed policies in code.
2. **Architecture audit**: map current booking/payment/wallet/dispatch/order/OTP/Flutter state transitions and lock ordering. Identify every direct status mutation.
3. **Ledger hardening**: immutable price snapshots, per-line ledger, aggregate checkout allocation, wallet source allocation, reconciliation records and constraints.
4. **Single booking flow**: 50% capture gate before dispatch; no regression to legacy bookings.
5. **Parent-order flow**: aggregate advance checkout, atomic allocations, one-worker assignment, partial-line handling.
6. **Urgent/same-day scheduling**: server capacity/lead-time policy, truthful availability windows, no hidden surcharge, reschedule support.
7. **OTP/service execution**: start and completion milestones, customer/worker auth, delivery, throttling, DB concurrency tests.
8. **Cancellation/refund/reschedule**: policy engine, platform failure, parent line cancellation, gateway refund events, support adjustments.
9. **Flutter integration**: customer and worker experiences, payment retries, balance due, refund status, urgent slot messaging and error recovery.
10. **Release readiness**: staging Razorpay test-mode scenarios, full regression, concurrency tests, reconciliation report, monitoring, rollback plan.

Do not proceed to the next phase merely because unit tests pass. Each phase needs API/integration tests and regression gates.

## 10. Minimum acceptance-test catalogue

- Scheduled, same-day, urgent, event-date, each fulfilment mode.
- Slot disappears between availability response and booking submit.
- Worker unavailable before dispatch, after offers, after acceptance, before start.
- 50/50 split for whole-paise, odd-paise, zero/low totals, discount/tax/add-ons/quantity.
- Capture only vs authorization, duplicate webhook, delayed webhook, wrong IDs, missing amount/currency, mismatched amount, capture after expiry.
- Wallet-only, gateway-only, mixed tender, wallet reservation rollback, duplicate reversal.
- Single booking and multi-line aggregate advance allocation, one paise mismatch, concurrent capture.
- All dispatch priority batches exhausted; one eligible worker for every order line; no worker common to all lines; overlapping line schedules.
- Start OTP wrong customer, wrong worker, wrong code, expired, replay, throttled, concurrent; direct status bypass.
- Completion OTP same negative cases; completion then final payment failure/retry.
- Customer cancellation just before, exactly at, and just after cutoff; UTC/IST boundary; same-day policy cases.
- ₹40 fee once, refund floor zero, multiple attempts, partial capture, wallet+gateway split refund.
- Platform cancellation full refund before start; worker no-show; customer no-show; late arrival; service dispute after start.
- Reschedule changes cutoff, assigned worker rejects, parent-order overlap after reschedule.
- Partial parent-line cancellation, all-lines cancellation, unaffected line balances.
- Refund requested/pending/processed/failed, duplicate/out-of-order events, retry and reconciliation.
- Legacy bookings/payment records remain readable and actionable.
- Flutter old/new app compatibility, killed app/network interruption, notifications fail, admin adjustment audit.

## 11. Product decisions requiring explicit approval

The following are not specified by the currently confirmed policy and must not be silently hard-coded:
1. Same-day/urgent cancellation: strict existing cutoff (no refund once booked same day) vs a short grace window before worker acceptance.
2. Minimum lead time and arrival-window/SLA per service and zone.
3. Customer and worker no-show grace periods, evidence requirements, and financial outcomes.
4. Whether urgent fee exists; if yes, exact amount/formula and who receives it.
5. Whether rescheduling is free, limited, or subject to a fee; how many reschedules are allowed.
6. Whether partial final-balance payments are allowed and any outstanding-balance collection/escalation policy.
7. Support/dispute resolution outcomes and who can authorize goodwill credits/refunds.
8. Whether the customer may change address/fulfilment mode after advance payment.

Until approved, safe defaults are: no hidden urgent fee; no invented SLA; no automatic no-show penalty; no late fee/auto-debit; no unapproved reschedule charge; route ambiguous cases to support and preserve the ledger.


## 12. Accepted-worker unavailability and dispatch exhaustion

The split-payment worker lifecycle now treats a worker who becomes unavailable after acceptance but before start-OTP verification as a reassignment event, not a direct cancellation:

- Worker must own the accepted assignment, provide a reason, and the service must not have started.
- Parent orders release every active line together and withdraw the order-level offer; completed/cancelled lines remain untouched.
- Captured advances and immutable financial plans remain in place while AIRway retries the existing Admin-configured priority batches.
- Every dispatch batch is persisted, including a batch with zero eligible workers. Empty batches are paced using the configured offer-expiry interval so the periodic task cannot consume all batches every minute.
- After the configured maximum batches are exhausted and no offer remains pending/accepted, split-payment bookings are platform-cancelled and every captured advance allocation is refunded in full, with no ₹40 customer-cancellation fee.
- Refunds reconcile separately by gateway and wallet tender. Missing/mismatched allocations leave the booking open for support reconciliation and generate an operations notification; they are never silently treated as refunded.
- A transient dispatch exception remains retryable. The periodic recovery task continues dispatch and applies the same terminal rule after the tracked batches are exhausted.
- After start OTP, automatic worker release/cancellation is blocked; support/dispute handling remains the approved path.

The dispatch-attempt ledger is read-only in Admin so operations can inspect batch number, candidate count, outcome, and retry timing.
