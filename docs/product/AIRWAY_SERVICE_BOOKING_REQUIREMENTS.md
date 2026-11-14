# AIRway — Service Booking Requirements Matrix

**Status:** Product requirements draft based on the launch catalogue seed master and current backend model  
**Launch categories:** Beauty, Car Wash, Electrical, Home Cleaning  
**Scope:** Customer discovery-to-booking questions, service-specific configuration, worker job brief, scheduling constraints, and positive/negative acceptance scenarios. Payment gateway, checkout payment method, refunds, commissions, and payout policy are explicitly out of scope for this phase.

> **Important catalogue boundary:** This document inventories the services declared by `seed_launch_catalogue.py`. The live database may contain admin-created, deactivated, renamed, or differently configured services. Before implementing the final dynamic flows, run a read-only export of active Service, FormField, ServiceVariant, AddOn, and category rows from the actual launch database and reconcile it against this master. Do not silently omit database-only services or publish unreviewed records.

---

## 1. Product principles

1. **Fast path first:** ask only what changes the provider, scope, duration, price, equipment, safety, or slot. Avoid asking the same thing twice.
2. **Progressive disclosure:** one short question per step where possible; reveal follow-up questions only when the answer requires them.
3. **Explain choices:** package cards show inclusions, duration, and price; add-ons show incremental price and time impact.
4. **No surprise charges:** customer sees fixed total or clearly labelled inspection/estimate process before confirming the booking request. Any extra work requires customer approval.
5. **Address and availability early enough:** check service-zone eligibility before the customer completes a long form; revalidate slot and worker eligibility on submission.
6. **Worker-ready job brief:** worker sees service, variant, customer answers, photos, add-ons, address/access notes, time, duration, and whether the job is fixed-price or quote-required.
7. **Accessible, respectful UX:** plain language, readable option cards, Hindi/English labels, no assumptions about gender, property ownership, or technical knowledge. Ask gender/audience only when it is genuinely required for the selected service/provider preference.
8. **Backend is the source of truth:** questions, options, variants, prices, durations, add-ons, and service availability come from API/database configuration. Flutter renders a reusable engine; it must not hardcode the catalogue.
9. **Safe escape route:** customer can go back, edit answers, remove extras, save/exit where supported, and contact support for an unclear or unsafe request.
10. **Never fake certainty:** quote-required services must not look like fixed-price services. If price or slot is unavailable, explain why and offer a useful next action.

## 2. Shared customer journey

| Stage | Customer experience | System/business rule |
|---|---|---|
| 1. Choose category | Beauty / Car Wash / Electrical / Home Cleaning | Show active launch categories only. |
| 2. Choose subcategory/service | Clear service names, relevant image, short description | API returns active services; hide unavailable city catalogue entries, but distinguish “not offered in your area” from “no worker/slot right now”. |
| 3. Configure service | Service-specific, minimal questions | Render active FormFields and conditional rules. Ask only required fields; optional fields are skippable. |
| 4. Select package/variant | Compare included work, duration, price | Only compatible active variants; do not show unrelated variants. |
| 5. Add optional extras | Add/remove extras with clear incremental cost/time | Validate add-ons belong to service; recompute price and duration. |
| 6. Review | Summary of selected service, answers, package, extras, scope, duration | Editable summary; show “fixed price” or “inspection/quote required” prominently. |
| 7. Address | Select saved address or add one | Validate address belongs to customer and is in an active zone. |
| 8. Date/time | Select available date and confirmed slot | Server is authoritative; recheck at submit to prevent race/conflict. |
| 9. Booking confirmation | Clear request/booking state and next step | Distinguish request submitted, worker assigned, and confirmed; do not imply worker acceptance before it occurs. |
| 10. Worker fulfilment | Worker accepts, arrives, starts, completes | Worker sees complete service-specific brief. Quote-required work pauses until customer approves estimate. |

**UX simplification:** if the selected service has no required questions, no variants, and no add-ons, skip those screens and go directly to address/schedule/review. Do not force every customer through empty steps.

## 3. Booking and pricing types

| Type | Use when | Customer flow | Price treatment |
|---|---|---|---|
| Fixed package | Defined work with known inclusions | Choose package → optional extras → schedule | Confirmed price shown before request. |
| Variant by attribute | Price depends on vehicle/property/item type | Select attribute → show matching package | Only variants matching selected attributes are selectable. |
| Quantity / per-unit | Number of items or measurable area changes work | Select unit/quantity/size → package | Show unit rate and calculated subtotal; validate minimum/maximum. |
| Inspection then quote | Scope/condition cannot be priced reliably before inspection | Describe issue + photos → book inspection | Show inspection/visit fee if configured; final work estimate is separate and requires approval. |
| Recurring / plan | Repeated visits over a period | Select frequency, duration, quantity, preferred schedule | Treat as a plan enquiry until recurrence, included visits, cancellation, and billing rules are explicitly configured. Do not model it as a one-off package accidentally. |

## 4. Category and service requirements

### 4.1 Beauty

**Default journey:** choose audience only if needed → choose service → choose package/finish if available → answer the one or two relevant questions → optional reference photo/add-on → address → date/time → review.

**Important UX:** do not ask “men or women?” as a generic first screen when the service itself already defines its audience. Respect the service's audience and any customer preference for a female professional. For sensitive services, use discreet labels and make photo upload optional unless a safe, operational reason makes it mandatory.

| Subcategory and seeded service inventory | Booking behaviour and required customer inputs | Optional inputs / conditional rules |
|---|---|---|
| **Hair Services:** Men's Haircut, Men's Hair Styling, Men's Hair Wash, Men's Haircut + Hair Wash, Men's Hair Colour, Grey Hair Coverage, Men's Hair Spa, Head Massage, Women's Haircut, Hair Trimming, Women's Hair Wash, Blow Dry, Women's Hair Styling, Hair Curling, Hair Straightening, Hair Smoothening, Keratin Treatment, Hair Rebonding, Women's Hair Spa, Global Hair Colour, Root Touch-up, Hair Highlights | Scheduled appointment. Where variants exist, choose the service package (e.g. regular/premium haircut, basic/deep/premium spa, root/global colour). | Hair length, current hair condition, desired style/colour, reference photo should appear only for chemical/colour/styling services where it helps the professional prepare. For colour/chemical work, show a consultation/patch-test disclaimer and do not promise results. |
| **Facial & Skin Care:** Face Cleanup, Fruit Facial, Gold Facial, Diamond Facial, Pearl Facial, Charcoal Facial, Hydrating Facial, Anti-Tan Facial, Brightening Facial, Bridal Facial, Face Bleaching | Scheduled appointment; choose an active facial package if packages are configured. | Skin type/sensitivity notes; ask about known allergies/sensitivity in a neutral optional note. Product/brand preference only if AIRway can actually fulfil it. |
| **Threading:** Eyebrow Threading, Upper Lip Threading, Lower Lip Threading, Chin Threading, Forehead Threading, Side Locks Threading, Full Face Threading, Threading Combination | Single-area services should be one-tap selection and proceed to schedule. Threading Combination requires selected areas. | Skin sensitivity/notes optional. Do not ask a second area question for a single-area service. |
| **Waxing:** Half Arms, Full Arms, Half Legs, Full Legs, Underarms, Full Face, Bikini Line, Bikini Wax, Brazilian Wax, Full Body Wax, Chest Wax, Back Wax | Select wax type/package if available (Regular/Rica/Premium); scheduled appointment. | Hair/skin sensitivity and product allergy note optional. Ensure provider capability and privacy preference for intimate/sensitive services before showing slots. Audience rules must not incorrectly hide a service from a customer where the service is legitimately offered. |
| **Manicure & Pedicure:** Manicure, Spa Manicure, Pedicure, Spa Pedicure, Gel Polish, Nail Art, Nail Extensions, Nail Removal | Scheduled appointment; choose finish/design/package only where configured. | Nail condition, polish removal, reference image, and design complexity only when relevant. Nail art/extensions may need a design/photo and duration selection. |
| **Makeup & Occasion Styling:** Party Makeup, Light Makeup, Engagement Makeup, Bridal Makeup, HD Makeup, Hairstyling, Bridal Hairstyle, Party Hairstyle, Saree Draping | Scheduled for standard occasion services. Bridal Makeup is quote/consultation flow; capture occasion and event date before proposing slots. | Preferred style, number of people, reference photos, getting-ready location/access, event start time. Multi-person booking must calculate duration and resource needs rather than treating people_count as a note only. |
| **Grooming & Massage:** Beard Trim, Beard Styling, Clean Shave, Hair Oil Massage, Foot Massage, Hand Massage, Back Massage, Full Body Spa | Scheduled for defined grooming/massage services. Full Body Spa currently uses inspection/quote mode in seed master and must remain quote-led until its scope and rates are approved. | Pressure/product preference and relevant comfort/access notes optional. Customer may state professional preference privately. |

**Beauty acceptance rules**
- Men/women audience restrictions are applied from the service configuration, not inferred from the customer's name or appearance.
- If a package is missing or has zero/unconfigured price, do not present it as bookable at ₹0; show “price being configured” / disable booking with a useful message.
- Bridal/quote services cannot be represented as an instant confirmed fixed-price booking.
- Reference photos are optional unless the service is explicitly a consultation request; upload failure must not block a service that does not require photos.
- Combined services must add their durations and only offer slots that fit.

### 4.2 Car Wash

**Default journey:** select service → select vehicle type → show only compatible package cards → optional extras → pickup/service location and access → date/time → review.

**Vehicle types in seed master:** Hatchback, Sedan, Compact SUV, SUV – 5 Seater, SUV – 7 Seater, MUV / MPV, Luxury Car, Luxury SUV.

| Subcategory and seeded service inventory | Booking behaviour and required customer inputs | Optional inputs / conditional rules |
|---|---|---|
| **Exterior Car Cleaning:** Exterior Car Wash | Required vehicle type; select Basic Exterior Wash, Deep Exterior Wash, or Premium Exterior Wash variant matching that vehicle. | Tyre Polish, Underbody Cleaning, Engine Bay Cleaning, Hard Water Stain Removal, Bird Dropping Removal. Explain any exclusions (e.g. engine bay only where safe/available). |
| **Interior Car Cleaning:** Interior Car Cleaning | Required vehicle type; choose Basic Interior Cleaning, Deep Interior Cleaning, or Premium Interior Cleaning variant matching vehicle. | Seat Shampoo, Leather Conditioning, AC Vent Cleaning, Roof Lining Cleaning, Odour Removal, Stain Removal. Ask fabric/leather only if it changes product/process. |
| **Complete Car Cleaning:** Complete Car Cleaning | Required vehicle type; choose Basic Complete Wash, Deep Complete Wash, or Premium Complete Wash matching vehicle. | No add-ons in seed master. Avoid asking interior/exterior separately because the selected package already defines both. |
| **Car Detailing & Paint Protection:** Rubbing & Polishing, Paint Correction, Wax Treatment, Ceramic Coating, Graphene Coating, Headlight Restoration, Scratch Reduction, Engine Bay Detailing | Inspection/quote. Required: vehicle type, vehicle condition. Book inspection/consultation; quote after checking actual condition and requested treatment. | Paint condition, photos, notes. Ask vehicle make/model/year and paint colour only if required to select products/compatibility. |
| **Monthly Car Wash Plans:** Monthly Car Wash Plan | Plan enquiry/quote. Required: vehicle type, number of vehicles, plan duration (15 days, 1/3/6 months). | Preferred frequency (Daily, Alternate Day, Weekly, 15-Day, Monthly), preferred service days/time window, number of locations/parking access. These must be structured plan terms, not just package title. |

**Car Wash acceptance rules**
- A Sedan package must not be selectable for an SUV; package attributes must be matched by vehicle_type.
- Changing vehicle type refreshes compatible variants and price; stale selection is cleared.
- Quantity/vehicle count must be bounded and validated.
- For pickup/drop, capture pickup and return/drop schedule separately only if AIRway truly provides vehicle pickup/drop; otherwise do not show it.
- If the car is not safely accessible or location disallows washing, offer a clear alternative rather than accepting an unusable booking.
- Detail treatments and monthly plans are enquiries/inspection/quote, not fixed instant bookings.

### 4.3 Electrical

**Default journey:** choose electrical service → choose work type (install/repair/replace/inspection) only if not already implied by the service → quantity → brief issue details/photo → property type/material responsibility → show visit/inspection fee or fixed service price → schedule.

**Safety first:** for smoke, fire, exposed live wiring, active sparking, electric shock, or water contacting live electrical equipment, show an urgent safety message: keep away, do not touch equipment, switch off power only if it can be done safely, and contact local emergency services/electricity provider where appropriate. Do not offer an ordinary time slot as if it were an emergency response service.

| Subcategory and seeded service inventory | Booking behaviour and required customer inputs | Optional inputs / conditional rules |
|---|---|---|
| **Fan Services:** Ceiling Fan, Wall Fan, Exhaust Fan, Decorative Fan | Work type, quantity, property type, material responsibility. For installation/replacement, ask whether fan is customer-supplied or needs supply; for repair ask symptom. | Mounting/ceiling height, regulator/switch issue, photo, brand/model. Ask ceiling height only if it affects ladder/equipment/safety. |
| **Lighting Services:** Bulb, LED, Tube Light, Panel Light, Ceiling Light, Wall Light, Chandelier, Decorative Lights, Outdoor Lights, Strip Lights | Work type, quantity, property type, material responsibility. | Light type/wattage, mounting height, indoor/outdoor, existing fitting, photo. Chandelier/high ceiling must trigger capability/height check before slot. |
| **Switch & Socket Services:** Switch, Socket, Switchboard, Plug Point, USB Socket, Doorbell, Loose Connection, Burnt Socket | Standard installation/replacement can be fixed only when clearly scoped. Loose Connection and Burnt Socket are inspection/quote in seed master. Capture quantity, property type, symptom and material responsibility. | Photo, board type, age/condition, notes. Burnt socket/sparking must show safety guidance and quote/inspection route. |
| **Wiring & Electrical Repairs:** New Wiring, Old Wiring Replacement, Wiring Repair, Short Circuit Diagnosis, Power Failure Diagnosis, MCB Installation, MCB Tripping Repair, Fuse Replacement, Earthing Work, RCCB / ELCB Installation, Voltage Fluctuation Diagnosis | Inspection/quote for new/old wiring, wiring repair, short circuit/power failure diagnosis, earthing, voltage fluctuation; fixed only for well-defined simple replacement/installation if price is configured. | Affected rooms/area, number of points, property type, photos, symptoms, access notes. For wiring, ask approximate area/room count and whether wall chasing/civil repair is needed. |
| **Inverter & UPS:** Inverter Installation, Inverter Repair, Inverter Wiring, Battery Installation, Battery Replacement, UPS Installation, UPS Repair, Charging Problem Diagnosis | Installation/replacement can be fixed only for defined scope; Inverter Repair, UPS Repair, Charging Problem Diagnosis are inspection/quote in seed master. | Inverter/UPS brand, capacity, battery count/type, current symptom, wiring requirement, photo. |
| **Geyser & Electrical Connections:** Geyser Installation, Geyser Electrical Connection, Geyser Switch Replacement, Geyser Power Problem, Water Pump Electrical Connection, Motor Wiring, Motor Starter Repair | Geyser Power Problem, Motor Wiring, Motor Starter Repair are inspection/quote. Other jobs require quantity, property type, material responsibility and installation/replacement context. | Appliance capacity/brand, mounting/location, water/electrical access, symptom, photos. |
| **Electrical Inspection & Setup:** Full Home Electrical Inspection, Electrical Safety Check, New Room Electrical Setup, Additional Power Point, Decorative Electrical Setup, Smart Switch Installation, Smart Light Installation | Full Home Electrical Inspection, Electrical Safety Check, New Room Electrical Setup, Decorative Electrical Setup are inspection/quote in seed master. Additional Power Point and smart installations require scope confirmation; do not imply final price if wiring/civil scope is unknown. | Number of rooms/points/devices, compatibility, Wi-Fi/smart-home ecosystem where relevant, property type, photos, preferred materials. |

**Electrical acceptance rules**
- The current seed uses a common question set for many electrical services. The final UI must make it conditional: e.g. “material responsibility” only for installation/replacement, “problem” only for repair/diagnosis, quantity where relevant.
- Do not ask a customer to diagnose a technical fault; use plain-language symptom options and “Not sure”.
- Quantity must be positive and capped; show unit (“fans”, “switches”, “points”) rather than generic “items”.
- Worker estimate must split labour, parts/materials, and any additional visit where configured. Customer approves/rejects before additional work begins.
- If customer rejects the estimate, worker must leave the site safely and booking must move to a defined declined-quote/cancelled state without collecting unapproved charges.
- Material supplied by customer vs worker must be explicit; no substitution without consent.
- Never expose a worker to a job outside verified skill, equipment, height, or safety capability.

### 4.4 Home Cleaning

**Default journey:** choose area/service → select package/depth → enter only the measurements that determine team size/time/price → add extras → show inclusions/exclusions → address/access → date/time → review.

| Subcategory and seeded service inventory | Booking behaviour and required customer inputs | Optional inputs / conditional rules |
|---|---|---|
| **Kitchen Cleaning:** Kitchen Cleaning | Required: number of kitchens, approximate size (Small/Medium/Large/Not sure), current condition (Light/Greasy/Heavy stains/Not sure). Choose Basic/Deep/Premium package. | Kitchen photos, chimney/fridge/microwave/oven/cabinet-interior add-ons. Make clear whether appliance interiors are excluded unless selected. |
| **Full Home Cleaning:** Full Home Cleaning, Move-in Cleaning, Move-out Cleaning | Required: bedroom count, bathroom count, cleaning type (Regular/Deep/Move-in/Move-out). Choose package where applicable. | Property size, furnished/unfurnished, occupancy, pets, heavy dirt, balcony/kitchen inclusion, photos. Move-in/out should have a scope checklist and may need inspection for unusually large properties. |
| **Bathroom Cleaning:** Bathroom Cleaning | Choose Basic/Deep/Premium; quantity of bathrooms required for multiple bathrooms and price/duration calculation. | Bathtub, exhaust fan, extra bathroom, hard-water stain treatment. Ask about water availability only if operationally necessary. |
| **Garden Cleaning:** Garden Cleaning | Choose Basic Garden Cleaning, Deep Garden Cleaning, or Garden Maintenance. Ask area size and whether work is cleanup or ongoing maintenance. | Grass cutting, hedge trimming, pruning, soil replacement, repotting, waste disposal. Ask waste disposal quantity/handling where charged. |
| **Bedroom Cleaning:** Bedroom Cleaning | Choose Basic/Deep/Premium; quantity of bedrooms if multiple rooms included. | Wardrobe interior, mattress, curtain, window, fan cleaning. Ask furniture/room condition only if it changes scope. |
| **Living Room & Dining Room:** Living Room & Dining Room | Choose Basic/Deep/Premium; number of rooms/areas where relevant. | Sofa, dining chair, window, glass cleaning add-ons. |
| **Sofa & Upholstery Cleaning:** Sofa & Upholstery Cleaning | Required: upholstery type (1/2/3/4 seater, L-shaped, U-shaped, recliner, dining chairs) and quantity. Choose Basic/Deep/Premium. | Photos, fabric/leather material, stain/odour notes. For mixed furniture, allow multiple line items rather than forcing one type for all. |
| **Mattress Cleaning:** Mattress Cleaning | Required: mattress size (Single/Double/Queen/King), quantity. Choose Basic/Deep/Premium. | Stain/odour/sensitivity note. |
| **Carpet & Rug Cleaning:** Carpet & Rug Cleaning | Required: size (Small/Medium/Large/Custom Size). Choose Basic/Deep/Premium. | Photo, exact dimensions for Custom Size, stain/odour notes. |
| **Balcony & Terrace Cleaning:** Balcony & Terrace Cleaning, Terrace Cleanup, Drain Area Cleaning, Outdoor Floor Cleaning | Ask balcony/terrace count or area size; choose suitable package where configured. | Photos, drain blockage/waste quantity, height/access, water source. Do not imply hazardous/high-rise exterior work is included. |
| **Window & Glass Cleaning:** Window & Glass Cleaning, Glass Door Cleaning, Balcony Glass Cleaning, Interior Glass Cleaning | Ask number/dimensions of accessible windows/glass panels and whether interior, exterior, or both. | Photos, height/access, hard-water stains. High-rise exterior glass work requires verified equipment/insurance/capability and should be blocked if not supported. |
| **Floor Cleaning:** Floor Cleaning, Tile Cleaning, Marble Floor Cleaning, Grout Cleaning | Ask area size (sq ft) and floor material; choose Basic Floor Cleaning or Deep Floor Scrubbing where applicable. | Photos, grout/stain condition, furniture movement. |
| **Inspection/quote exception:** Marble Polishing | Inspection/quote; required area size and photos strongly recommended before visit. | Marble type/condition, previous polishing, access and furniture movement. No fixed package promise until site assessment. |

**Home Cleaning acceptance rules**
- Quantity and area are not generic notes: use structured number/unit inputs and calculate duration/price according to backend rules.
- Package inclusions/exclusions must be visible before selection. “Deep cleaning” must not be an undefined marketing label.
- A selected add-on such as extra bathroom must increase both amount and estimated duration.
- For a very large property or custom area, switch to inspection/quote rather than underquoting.
- Ask about pets, fragile items, access, water/power only when it materially changes worker preparation or safety.
- Do not guarantee removal of permanent stains, damage, mould, or specialist contamination unless the service is explicitly supported.

## 5. Worker job brief requirements

Every worker offer/job detail must include:
- Service and category name; selected package/variant; booking type (fixed / inspection / quote / plan enquiry).
- Customer's structured answers in human-readable labels, not raw JSON keys.
- Quantity and units; included tasks; selected add-ons; photos and customer notes.
- Address, locality/zone, access instructions, customer contact through approved in-app channels.
- Scheduled start, expected duration, buffer, and any separate pickup/drop visit times.
- Material responsibility and equipment/height/access/safety flags where relevant.
- Price context: fixed customer-approved scope, visit fee if any, or “estimate required”; never instruct worker to collect an unapproved amount.
- Worker actions: accept/decline with reason, navigate/contact, mark arrived, start, submit estimate where permitted, record work notes, mark completion, upload evidence if required.

**Quote workflow:** worker records scope → labour → parts/materials → taxes/other approved components → total and validity → customer receives clear estimate → customer approves or rejects → only approval unlocks work beyond any explicitly pre-approved inspection. Record who approved and when. No silent price edits.

## 6. Shared positive and negative scenario catalogue

| Area | Positive scenario | Negative / edge scenario and expected behaviour |
|---|---|---|
| Catalogue | Active service and packages load for selected city | Inactive service/category hidden; no services shows accurate city/category message |
| Questions | Required answers complete; conditional question appears only when relevant | Missing/invalid answer blocks next step with field-level explanation |
| Options | Variant matches selected vehicle/size/audience | Changing earlier answer invalidates incompatible variant and asks customer to reselect |
| Add-ons | Add/remove updates amount, time and summary | Inactive/wrong-service add-on rejected by backend; UI selection cleared with explanation |
| Photos | Supported photo uploads and preview works | Upload fails/oversize/unsupported format: retry; do not lose other answers |
| Address | Valid active-zone address selected | Outside zone / deleted / someone else's address: stop before final request and explain |
| Schedule | Server confirms slot and duration fits | Past slot, worker conflict, slot taken during checkout, or worker unavailable: refresh slots and ask customer to choose |
| Worker dispatch | Qualified online worker receives full job brief | No eligible worker / all decline / offers expire: communicate honestly and allow new slot/support/cancel |
| Fixed price | Price matches selected configuration | Zero/unconfigured price: disable paid confirmation; never charge ₹0 or guess |
| Quote | Worker submits itemized estimate; customer approves | Customer rejects/does not respond; work remains blocked and defined timeout/exit process applies |
| Scope change | Customer requests extra; worker submits revised estimate | Worker cannot add work/charge without explicit approval |
| Cancellation | Customer sees policy before confirming cancellation | Too-late cancellation or worker already arrived follows clearly stated policy; no hidden fee |
| Worker capability | Matching approved worker with required skill/zone/slot | Unverified skill, unsafe height/equipment, or service mismatch: no offer |
| App/network | Retry resumes without duplicate booking | Double tap/retry must not create duplicate bookings or offers; use idempotency protection |
| Language/accessibility | Hindi/English labels and screen-reader-friendly controls | Missing translation falls back to English; no blank labels or inaccessible image-only choices |

## 7. Backend and API requirements

The current catalogue already has useful primitives: Category, Service, ServiceVariant, AddOn, FormField, CityService, ServiceImage; bookings persist customer_answers, BookingFormResponse, BookingAddOn, pricing_snapshot, status history, and worker offers. Reuse these before adding new tables.

Required improvements before the dynamic engine is considered complete:
1. Add explicit conditional visibility/dependency rules to FormField (e.g. show problem only for Repair; show vehicle condition only for inspection quote) and validated option values.
2. Add field metadata for unit, min/max, help text, placeholder, input validation, privacy classification, and whether an answer is shown to the worker.
3. Add explicit pricing strategy/configuration per service: fixed, per-unit, attribute-based, inspection fee + quote, recurring plan. A `pricing_type` alone is insufficient for area/quantity/recurrence formulas.
4. Add explicit service capability/worker skill requirements beyond a simple WorkerService link if equipment, certifications, gender preference, or multi-worker team is required.
5. Validate all required active FormFields server-side, not only fields the client happens to send. Validate option values, number bounds, file ownership/type/size, and that each variant/add-on is active and belongs to the service.
6. Validate variant attributes against the submitted answers (e.g. vehicle_type) and reject stale/incompatible selections.
7. Recalculate duration and price server-side from the selected variant, quantities, and add-ons; never trust Flutter totals.
8. Persist a full immutable service/answer/package/add-on snapshot in the booking/order item so later catalogue edits do not rewrite a past booking.
9. Add explicit quote/estimate entities and status transitions before enabling worker quote submission.
10. Support multi-line scope items for mixed quantities (e.g. 2 sofas + 1 recliner) and multiple services without forcing a single generic quantity field.
11. Add idempotency and transactional slot revalidation at booking submission; a slot shown as free can be taken before the customer confirms.
12. Distinguish catalogue publication, city serviceability, and real-time worker/slot availability in API responses and UI copy.
13. Add audit events for answer edits, estimate revisions, customer approvals, cancellations, and worker assignment.
14. Define recurrence rules separately for monthly plans; current one-off booking date/time is not enough.

## 8. Flutter dynamic booking engine requirements

Build reusable components, not a separate hardcoded screen for every service:
- `ServiceFlowResolver`: resolves flow type and steps from service configuration.
- `QuestionStepRenderer`: select cards, text, number, textarea, photo, quantity/unit, date/time.
- `VariantSelector`: compatible package cards with inclusions, duration, price.
- `AddOnSelector`: optional extras with incremental price and duration.
- `BookingReview`: complete editable summary and price/quote disclosure.
- `AddressSelector` and `ScheduleSelector`: shared existing components.
- `BookingProgress`: short, accurate progress and recoverable back navigation.

The same engine should support all active services through backend configuration. Service-specific branching is data-driven; only genuinely unique workflows (e.g. recurring plan, inspection/quote, vehicle pickup/drop) get specialised step components.

## 9. Release gates and acceptance checklist

Do not replace the current booking screens until:
- [ ] Live active catalogue export is reconciled against the seed master.
- [ ] Every active service is assigned one booking/pricing type.
- [ ] Every required question has a reason, type, validation, and customer-friendly label.
- [ ] Every variant has compatible attributes, included work, duration, and approved non-zero price (or is explicitly unpublished).
- [ ] Every add-on has service ownership, price, and duration impact.
- [ ] Quote-required services have worker estimate + customer approval lifecycle.
- [ ] Worker job brief has been tested for every booking type.
- [ ] Positive and negative tests cover all scenarios in Section 6.
- [ ] Existing date/time, booking, tracking, cancellation, and worker assignment regressions pass.
- [ ] Payment gateway and payment policy are reviewed separately after this booking requirements phase.

## 10. Implementation sequence

1. Export and reconcile actual active launch catalogue.
2. Review this matrix service-by-service; resolve any ambiguous service scope with business owner.
3. Approve booking type, required questions, package inclusions, add-ons, price formula, duration, worker skills, and quote policy.
4. Complete backend configuration and validation contracts.
5. Implement Flutter dynamic step engine against API contracts.
6. Implement worker-side job brief and quote approval.
7. Test every service flow and all positive/negative cases.
8. Only then review payment, refunds, cancellation fees, commissions, worker payouts, and customer receipts as a separate business requirements phase.

---

## Source files audited

- `backend/apps/catalog/models.py` — category, service, variants, add-ons, form fields, city mapping.
- `backend/apps/catalog/serializers.py` and `views.py` — API shape and catalogue availability.
- `backend/apps/catalog/management/commands/seed_launch_catalogue.py` — four-category seeded service master and current default questions/packages.
- `backend/apps/bookings/models.py` and `serializers.py` — booking snapshots, form responses, add-ons, order items, and current validation shape.
- `backend/apps/bookings/dispatcher.py` and `backend/apps/workers/models.py` — worker eligibility, service mapping, schedules, leave, and offers.

**Not yet verified:** actual live database row inventory, approved commercial prices, worker certifications/equipment, final cancellation policy, recurring plan fulfilment, and estimate/payment policy. These are explicit review items, not assumptions.
