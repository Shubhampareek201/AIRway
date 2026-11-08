# AIRway — Customer Booking, Worker Dispatch & Assignment PRD

**Status:** Product/engineering decision document  
**Scope:** Customer booking and checkout, worker eligibility, offer delivery, acceptance/decline/expiry, scheduling, assignment, order pricing, cancellations, exceptions and operational controls.  
**Launch geography:** Rawatbhata first.  
**Launch service roots:** Beauty, Car Wash, Electrical and Home Cleaning.  
**Dispatch strategy selected by founder:** priority_batch.  
**Core invariant:** A multi-service order is offered to, accepted by and assigned to one worker who is eligible for every line in that order.

This document is the decision baseline for implementation. It separates confirmed product decisions from policies that need explicit business approval. It does not authorize inventing customer prices, worker payouts, commission, refunds, cancellation fees, travel/material charges or tax treatment.

## 1. Product outcomes and non-negotiable rules

1. A customer should understand exactly what they are booking, where, when, what is included and what it costs before submitting.
2. A worker must never receive a job they cannot perform in full.
3. A customer must never be shown a slot as confirmed unless the backend can validate it.
4. A multi-service order is one assignment unit: one worker, all service lines, one order-level acceptance decision.
5. The first valid acceptance wins. All competing pending offers for that order are withdrawn atomically.
6. No price is silently changed after checkout. Any price adjustment must be explained and explicitly accepted by the customer before payment/work proceeds.
7. Dispatch, customer-visible availability and Admin preview are separate concepts:
   - Admin preview can inspect the entire master catalogue.
   - Worker capability approval controls whether a worker is eligible.
   - Customer bookability depends on an active service, service-area coverage and at least one approved eligible worker for the requested slot.
8. All state transitions are server-authoritative, auditable and idempotent.
9. Payment policy is deliberately not changed by this dispatch PRD.

## 2. Actors and permissions

| Actor | May do | Must not do |
|---|---|---|
| Customer | Browse eligible catalogue, build cart, choose address/times, submit, track assignment, accept/reject any future quote, pay, request cancellation/support | Select an ineligible worker; alter server prices; treat an unconfirmed slot as reserved |
| Worker | Set online/offline, maintain schedule, declare skills/services/equipment/areas, view own offers, accept or decline pending offers, manage an accepted job under defined job-state rules | Accept if not eligible/available; see another worker's private data; change customer price |
| Admin/Ops | Approve worker profile, documents, capabilities, service areas; configure catalogue and dispatch; intervene with audited reason; view queues and exceptions | Bypass safety/eligibility silently; edit historical price snapshots without audit |
| System | Validate, rank, batch, expire, assign, notify, reconcile and log | Assign two workers to the same booking/order or accept stale offers |

## 3. Customer journey and decisions

### 3.1 Browse and serviceability

- Keep the complete master catalogue visible in Admin preview even if no worker currently supports a service.
- Customer catalogue only exposes services configured active for the selected city/zone and deliverable by at least one approved worker.
- An active service with no approved worker must be labelled unavailable in Admin/Ops; it must not appear as bookable to customers.
- Category audience (Men/Women/Both) is not the same as worker gender preference.
- Show package inclusions, exclusions, duration, price basis, add-ons and any mandatory information before adding to cart.
- Never use a generic/mismatched service image as if it represents the service.

### 3.2 Cart and address

- Cart is a draft; it does not reserve worker capacity or a slot.
- Every order uses one selected service address and zone. Changing address must revalidate every cart line.
- If an order needs multiple addresses, split it into separate orders; do not dispatch one worker across unrelated addresses by accident.
- Cart line captures service, variant/package, quantity, add-ons and answers. Backend recalculates every price.
- Reject duplicate cart line identifiers, missing lines, inactive services/variants/add-ons, mismatched variant/service, invalid answers and out-of-range quantities.
- At checkout, freeze service/variant/add-on names and amounts into immutable booking/order snapshots.

### 3.3 Time selection and checkout

- Address first, then API-confirmed date/time.
- A slot shown as available is provisional until checkout revalidates it under transaction/locking.
- Duration must use the selected variant/package duration, quantity, service buffer and pickup/drop windows.
- For a multi-service order assigned to one worker, service windows must not overlap, including configured buffers. Reject overlapping cart schedules before creating the order; ask the customer to choose different times.
- Different days are allowed if the same worker is eligible and available for every line.
- Checkout validates all lines first. If any line fails, fail the whole checkout; do not create a partial order or silently drop a line.
- Checkout response must clearly say whether offers were sent or the order is waiting for assignment. A created order is not an assigned job.

### 3.4 Customer order tracking

Show one parent order with:
- all service lines, selected package, quantity and answers summary;
- address and each appointment/pickup/drop time;
- line price, tax and order total;
- status of assignment (waiting, offers in progress, assigned, needs support);
- assigned worker only after acceptance;
- payment action only when every line has been assigned and the order is eligible for payment.

Never show a worker as assigned because an offer was merely sent.

## 4. Worker onboarding and eligibility

A worker is dispatch-eligible only when all mandatory gates pass:

1. Worker profile is approved and not suspended/rejected.
2. Worker is online at dispatch and still online/approved at acceptance.
3. Required identity/document checks are approved according to Admin policy.
4. Worker has an Admin-approved capability for every requested service and any required variant, skill, equipment or specialization.
5. Worker is approved for the order's service zone.
6. Worker schedule covers every appointment interval.
7. Worker has no leave, blocked slot, existing assignment or other conflict.
8. Worker satisfies explicit service constraints, such as a requested female professional.
9. Worker is not the customer.
10. All lines in a parent order are compatible with the same worker and do not overlap.

**Capability model recommendation:** distinguish service capability from variant/skill/equipment capability. A worker approved for basic facial must not automatically be eligible for advanced/bridal facial unless the capability record explicitly covers it. Admin approval, not a worker's self-selection alone, makes a capability dispatchable.

Worker onboarding should allow a worker to declare capabilities, zones, working hours, equipment and experience. These declarations remain pending until Admin approves them. Adding a new approved capability should automatically make the worker eligible for matching future jobs; it must not rewrite an already accepted job.

## 5. Dispatch strategy — priority_batch

### 5.1 Batch lifecycle

1. Build the eligible worker set using the intersection of eligibility for every order line.
2. Sort eligible workers by the currently selected Admin priority strategy.
3. Exclude every worker who has already received an offer for this order.
4. Send offers to the first configured batch.
5. All workers in the current batch may accept; first valid acceptance wins.
6. Do not send the next batch while at least one current-batch offer remains pending and unexpired.
7. When every offer in the batch is declined, withdrawn, expired or otherwise invalid, advance to the next batch.
8. Stop after the Admin-configured maximum batches or when no new eligible workers remain.
9. A periodic recovery task may retry orders with no pending/accepted offer, but must respect the same batch count and never duplicate an active offer.

### 5.2 Admin configuration

Admin controls:
- dispatch enabled/disabled;
- batch size;
- maximum batches;
- offer expiry duration;
- priority strategy.

Available initial priority strategies:
- highest rating first;
- highest acceptance rate first;
- rating then acceptance rate;
- fewest cancellations then rating.

Recommended launch default: **rating first**, then stable tie-break by worker ID, until the platform has enough trustworthy acceptance/cancellation data. Revisit after real operating data exists. Avoid opaque weighted scores at launch.

Admin should see the exact current strategy and limits, plus the number of offers sent, pending, accepted, declined, expired and remaining eligible workers.

### 5.3 Offer card and notification

Worker offer details must include:
- complete order summary, not just the anchor booking;
- all services/packages, quantities and durations;
- appointment times for every line;
- service address/zone and navigation entry point;
- customer instructions and required equipment/material notes;
- worker earning estimate only when a real payout calculation has been approved;
- offer expiry countdown and accept/decline actions.

Do not expose customer phone/address before the platform's approved privacy point. Decide and implement the exact disclosure point before launch.

### 5.4 Accept

On accept, server rechecks all gates. Then, in one transaction:
- lock parent order first, then offer and booking rows in a consistent order;
- verify offer belongs to worker, is pending and unexpired;
- verify order is still awaiting assignment;
- verify service active state, capabilities, zone, worker status, schedule, leave, blocked slots and assignment conflicts for every line;
- create assignment for every booking line to the same worker;
- update every booking status/history;
- mark accepted offer accepted;
- withdraw every competing pending offer for the order;
- update parent order to awaiting payment only after all lines are assigned;
- create customer and worker notifications.

If any line fails validation, reject the entire acceptance; never partially assign an order.

### 5.5 Decline, expiry and no response

- Decline affects only that worker's offer. It does not penalize the worker automatically.
- Do not advance the batch until all offers in the current batch are no longer pending.
- Expiry is server-enforced; a late accept receives an expired response.
- If every batch is exhausted, order remains awaiting assignment and enters an Admin/Ops exception queue. Customer sees a clear message and support/retry route.
- Do not auto-cancel or charge the customer because no worker accepted.

### 5.6 Worker goes offline or capability is revoked

- Going offline after an offer is sent should prevent acceptance; expire/withdraw the offer and continue once the current batch is exhausted.
- Admin suspending a worker or revoking a capability invalidates pending offers for affected orders.
- An already accepted job must not be silently removed. It enters an Admin-managed reassignment/cancellation process with customer notification and an audit reason.

## 6. Scheduling, overlap and capacity rules

### 6.1 Two types of conflict

- **Service capacity conflict:** the service may have its own global/branch capacity, independent of a specific worker.
- **Worker conflict:** one worker cannot perform two overlapping jobs.

These are different checks and must not be conflated.

### 6.2 Required interval rules

Use half-open intervals [start, end) so one job ending exactly when another starts is not an overlap, unless a service buffer makes it overlap.

Include:
- variant duration;
- quantity multiplier where business semantics say quantity adds duration;
- service buffer/turnaround;
- pickup and drop windows;
- existing active assignments;
- worker shifts, leave and blocked slots;
- timezone-aware local display and UTC storage.

For pickup/drop services, confirm whether the worker is occupied for the entire pickup-to-drop interval or only pickup/drop visits plus travel/handling windows. Do not assume the worker is free in between until the operating model is decided.

### 6.3 Race conditions

- Two customers checking the same slot at once: database-level transactional protection or a reservation/capacity lock is required; a pre-check alone is insufficient.
- Two workers accepting different offers for the same order: order-first row lock; only one can win.
- Same worker accepting two overlapping jobs simultaneously: worker-level lock or equivalent transactional conflict guard is required; checking availability without serializing concurrent accepts can race.
- Customer cancels while worker accepts: serialize against the booking/order state; one transition wins, the other receives a conflict response.
- Expiry task and accept at the same instant: lock offer/order and evaluate expiry with server time; exactly one terminal transition wins.
- Retry task and manual decline: dispatch under parent booking/order lock; unique constraints prevent duplicate offers.

## 7. Price, cost and worker earnings

### 7.1 Customer price integrity

Checkout must calculate server-side:
- package/variant base price;
- quantity;
- add-ons and their quantities;
- visit/inspection fee if configured and approved;
- discount/promo only when validated;
- tax according to approved tax configuration;
- final total and currency.

Every order item stores an immutable price snapshot. A catalogue price change after checkout affects new orders only.

### 7.2 Cost transparency

Customer review should display:
- service/package amount;
- quantity;
- add-ons;
- visit/inspection fee, if any;
- discount;
- tax;
- total payable;
- fixed-price vs inspection/quote status.

No surprise materials, travel, parking, extra work or after-visit charges. If a service needs variable materials or inspection-based pricing, the customer must see the rule before booking and approve any revised quote before payment/work proceeds.

### 7.3 Worker earnings and platform economics

Before launch, define separately:
- worker gross earning per line;
- platform commission/fee;
- worker travel/visit reimbursement;
- material reimbursement and proof;
- taxes/withholding on worker payout;
- cancellation/no-show compensation;
- payout schedule and minimum payout threshold;
- dispute/chargeback reserve, if any.

Never derive worker earnings from the customer total by guesswork. Do not show a worker an earning estimate until the payout engine is implemented and tested. Keep customer price, platform revenue and worker payable as separate ledger values.

### 7.4 Pricing decisions requiring finance approval

The current checkout code contains a hard-coded 18% tax calculation. Confirm the applicable tax treatment and whether prices are tax-inclusive or tax-exclusive with finance/accounting before launch. Do not treat this implementation detail as legal/tax approval.

## 8. Cancellation, reschedule, no-show and service completion

Recommended lifecycle rules (business approval required before coding fees/refunds):

| Situation | Recommended product behavior |
|---|---|
| Customer cancels before any worker accepts | Cancel whole order; withdraw all pending offers; no worker payout |
| Customer cancels after worker accepts but before travel/start | Apply a clearly disclosed cancellation window/fee only after approved policy; notify worker and customer |
| Customer cancels after worker starts/travels | Use approved arrival/visit compensation policy; require timestamps/evidence |
| Worker cancels before starting | Keep customer price unchanged; re-dispatch to another fully eligible worker; notify customer |
| Worker cancels after starting | Ops intervention; customer safety and service recovery first |
| Worker no-show | Customer can report; log evidence; Ops reassign/refund under approved policy |
| Customer no-show/unreachable | Worker follows a defined contact/wait protocol; never invent a fee |
| Reschedule before assignment | Revalidate all service lines and dispatch fresh offers |
| Reschedule after assignment | Require worker availability and customer confirmation; atomic update of all affected lines |
| Partial line cancellation | Do not silently keep the same order/worker if remaining order changes eligibility; recompute assignment and total, then confirm with customer |
| Work partially completed | Record per-line/per-stage completion and evidence before any partial settlement/refund |

Accepted-worker withdrawal must be a separate job-cancellation/reassignment workflow, not the same endpoint as declining an unaccepted offer.

## 9. Exception and abuse scenarios

- No eligible worker: retain order in awaiting assignment; customer sees honest status; Ops sees reason and eligible-worker count.
- Only one eligible worker: send one offer; no fake batch fill.
- Worker accepts after expiry: reject.
- Worker accepts after Admin suspension: reject.
- Worker capability removed between offer and acceptance: reject and continue dispatch.
- Worker schedule edited after offer: revalidate on accept.
- Customer changes address/time/quantity after offer: invalidate existing offers and re-dispatch after revalidation.
- Duplicate network request: idempotent response; never duplicate booking, assignment or payment.
- Notification delivery failure: offer remains queryable in worker app; retry notification without duplicating offer.
- App closed/offline: expiry still enforced server-side.
- Malformed or tampered price: reject; server snapshot wins.
- Service deactivated during dispatch: stop new offers and invalidate pending offers; accepted jobs go through Ops review, not silent cancellation.
- Fraudulent worker/customer behavior: rate-limit, audit and escalate; do not silently change eligibility scores without a documented policy.
- All Admin overrides record actor, timestamp, before/after values and reason.

## 10. Status model and state transitions

### Order

- awaiting_assignment: no worker has accepted the full order.
- awaiting_payment: every booking line has an assignment; payment may be initiated under payment rules.
- paid: payment settled.
- partially_cancelled: only after partial-cancellation rules and accounting are implemented.
- cancelled: whole order cancelled.

### Offer

- pending → accepted, declined, expired, or withdrawn.
- No transition out of a terminal offer state.
- Accepted offer remains accepted as historical evidence even if the job is later cancelled; job cancellation is recorded on the booking/order, not by rewriting acceptance history.

### Booking

- pending → confirmed → assigned → in_progress → completed.
- Cancellation/dispute transitions must be audited and must reconcile all lines in a parent order.

## 11. Operational dashboards and metrics

Admin/Ops needs:
- orders waiting for assignment and age in queue;
- no-eligible-worker reason by service/zone/slot;
- eligible worker count and batch progression;
- offer accept/decline/expiry rates;
- time to first offer, time to acceptance, time to assignment;
- worker acceptance rate with sample size (avoid overreacting to one job);
- worker cancellations/no-shows and customer cancellations;
- assignment conflicts and failed acceptance reasons;
- price adjustments, refunds, worker payable and platform margin;
- notification failures and stuck orders.

Use these metrics to tune batch size, expiry and priority. Do not optimize solely for acceptance speed if quality, safety or fairness degrades.

## 12. Launch acceptance criteria

- [ ] One-service order dispatches and accepts normally.
- [ ] Multi-service order only offers to the intersection of all eligible workers.
- [ ] One accepted offer assigns every line to the same worker.
- [ ] Simultaneous competing accepts produce exactly one winner.
- [ ] Worker cannot accept if any line is unsupported, out of zone, outside shift, blocked, on leave or overlapping.
- [ ] Two order lines with overlapping intervals/buffers are rejected before order creation.
- [ ] Different non-overlapping dates/times can be assigned to the same worker.
- [ ] Decline/expiry/withdrawal advances only after the whole current batch is exhausted.
- [ ] No worker is offered twice for the same order.
- [ ] Batch limits and expiry come from Admin settings.
- [ ] Disabled dispatch creates no offers and does not break checkout.
- [ ] Worker going offline/suspended or capability revoked before acceptance is handled safely.
- [ ] Customer cancellation and worker cancellation do not leave orphan pending offers or assignments.
- [ ] Cart price tampering is ignored; checkout snapshots are server-calculated.
- [ ] Price/tax/fee snapshots reconcile with the final order and payment amount.
- [ ] Payment is unavailable until all order lines are assigned.
- [ ] Notification failure does not lose an offer.
- [ ] All status transitions are auditable and idempotent.
- [ ] Full customer and worker app journeys are tested on real devices and slow/offline networks.

## 13. Current implementation audit — known gaps

1. Parent-order priority_batch dispatch and same-worker assignment have been implemented, but need another full regression run after the latest changes.
2. WorkerOffer.booking migration state drift was detected by makemigrations --check; migration 0009 was added to align its help text.
3. Two existing tests expected HTTP 400 for an already-assigned offer; endpoint was changed back to 400 to preserve the established API contract.
4. Checkout now rejects overlapping service windows before creating the parent order. A regression test was added.
5. Worker priority choices are configurable, but rating/acceptance/cancellation data quality and minimum sample size are not yet governed.
6. Standalone dispatch now serializes on the booking row; parent-order booking lines are routed to order-level dispatch and cannot be individually confirmed. Regression coverage is being added for this invariant.
7. Existing customer cancellation is booking-level. Parent-order cancellation, partial cancellation and accepted-worker reassignment are not yet a complete unified workflow.
8. Worker acceptance of a parent order does not create a booking-linked Razorpay order; parent-order payment is a separate customer flow. Keep this distinction explicit.
9. The current checkout calculates 18% tax in code. Finance must approve the actual tax treatment before launch.
10. Customer order tracking currently exposes basic line status and worker identity; the full live dispatch timeline, batch progress and support exceptions still need product/UI work.
11. Worker offer payload now contains order service details, but worker app must be updated to render the complete order and prevent treating it as one standalone anchor booking.
12. Notification delivery, worker online changes, capability revocation, cancellation races and same-worker concurrent acceptance still need dedicated tests.
13. The current worker model has service and zone links, but does not yet prove a complete approved capability matrix for every variant, skill or required equipment.
14. Worker payout, commission, travel/material charges, cancellation fees, refund rules and payout timing are not specified and must not be guessed.

## 14. Decisions recommended for founder approval before payment/cancellation implementation

1. **Single worker per multi-service order:** recommended and already selected for current implementation. If a customer wants different workers, create separate orders.
2. **Overlapping service lines:** reject checkout and ask the customer to choose separate times. Recommended and implemented.
3. **Offer expiry:** Admin-controlled; launch default currently 5 minutes. Validate using actual worker response data.
4. **Dispatch batch size/max batches:** Admin-controlled; current defaults are 5 workers × 3 batches. Tune only from operational data.
5. **No worker accepts:** leave order awaiting assignment and route to Ops/customer support; do not auto-charge or silently cancel.
6. **Price changes after booking:** no silent increase. Any quote revision requires explicit customer approval.
7. **Tax, commission and worker payout:** require finance-approved calculation and ledger before launch.
8. **Cancellation and no-show fees:** disclose before booking and apply only after the founder approves exact windows, amounts and evidence rules.
9. **Customer/worker contact disclosure:** approve the exact point in the journey at which phone/address details become visible.
10. **Inspection/quote services:** do not charge a variable final amount until inspection findings, quote breakdown, expiry and customer approval are recorded.

---

**Implementation rule:** Each item above must be mapped to code, API contract, Admin control, customer UI, worker UI, notifications and automated tests. A scenario is not complete merely because the backend returns a status code.
