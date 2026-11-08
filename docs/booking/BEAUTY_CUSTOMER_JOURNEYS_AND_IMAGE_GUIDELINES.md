# AIRway Beauty — Audience, Service Taxonomy, Booking Journeys & Image Rules

> Status: Product-design proposal for review. This document does not approve catalogue activation, worker capability, prices, packages, visit fees, or salon policies. The current catalogue snapshot is documented separately in `SERVICE_BY_SERVICE_BOOKING_REQUIREMENTS_MATRIX.md`.

## 1. Customer entry: choose who the service is for

When a customer opens **Beauty**, show three large photo cards:

1. **Men** — a clear, premium salon portrait of a man.
2. **Women** — a clear, premium salon portrait of a woman.
3. **Both** — a balanced photo showing a man and a woman, labelled **Unisex services**.

Use the customer's selection only to filter the catalogue. Do not infer the choice from the customer's name, profile, gender, phone number, or the type of service. Keep the selected audience for the current browsing/booking journey and make it easy to go back and change it.

"Both" means services deliberately configured as unisex and actually deliverable by an appropriately trained professional. It must not mean "show every service". A service should appear in more than one audience only when its scope, equipment, products, professional capability, privacy arrangements, and price are suitable for each audience.

## 2. Proposed Men's Beauty experience

Use familiar, simple names and organise the Men's page around what a customer is trying to get done.

### A. Haircut & Beard
- Men's Haircut
- Haircut + Hair Wash
- Hair Wash
- Hair Styling
- Beard Trim
- Beard Shape & Styling
- Clean Shave
- Hair Colour
- Grey Hair Coverage
- Hair Spa

Suggested booking details only where relevant:
- Haircut: preferred length/style (short, medium, long, not sure) and optional reference photo.
- Beard: trim only, shape and define, full beard styling, clean shave.
- Hair colour: root touch-up or full colour; current hair colour/grey coverage; optional reference photo; allergy/patch-test acknowledgement according to salon policy.
- Hair spa: basic/deep/premium package, hair/scalp concerns if the professional needs them.

### B. Face & Skin Care
- Face Cleanup
- Blackhead & Whitehead Removal
- Detan (Face & Neck)
- Face Facial
- Brightening Facial
- Deep Cleansing Facial
- Charcoal Facial
- Face Bleach (only if supported and clearly described)

Keep "blackhead removal" as a clearly described skin-cleaning treatment, not a medical extraction promise. Do not promise treatment of acne, infection, scars, or other medical conditions.

Suggested details: skin sensitivity/allergy notes (optional), known product reaction (optional), selected facial package, and an optional reference/photo only when useful. Ask only the minimum needed for safe service delivery.

### C. Body Grooming
- Arms Hair Removal
- Chest Hair Removal
- Back Hair Removal
- Underarm Grooming
- Body Hair Trimming
- Manicure
- Pedicure
- Spa Manicure / Spa Pedicure

Make the area explicit (half/full arms, chest, back, underarms, etc.). Do not label a service simply "Arms Clean" if it is unclear whether this means waxing, trimming, or another method. Let the customer choose the actual method where the salon offers more than one.

### D. Massage & Relaxation
- Head Massage
- Hair Oil Massage
- Shoulder & Back Massage
- Foot Massage
- Hand Massage
- Full Body Spa (only if the business has verified trained staff, privacy arrangements, service boundaries, and the required equipment)

Show duration and what body area is included before the customer books. Do not combine massage types or body areas into an unclear generic package.

### E. Groom's Wedding & Special Occasion
Create a dedicated **Groom Packages** collection rather than hiding wedding grooming inside ordinary haircut or facial services.

Possible bookable components:
- Groom Haircut & Styling
- Beard Styling / Clean Shave
- Face Cleanup / Detan
- Groom Facial
- Hair Spa
- Manicure & Pedicure
- Body Grooming (customer chooses only the areas offered)
- Wedding-Day Hair & Beard Finish
- Pre-Wedding Grooming Plan (multiple visits)

Possible package structure (scope must be confirmed before publishing):
- **Groom Essential** — haircut, beard finish and basic cleanup.
- **Groom Premium** — haircut/styling, beard styling, selected facial/cleanup and hand/foot grooming.
- **Groom Royal** — a coordinated multi-service preparation plan with agreed visits and wedding-day finishing.

The package builder must show each included service, duration, number of visits, exclusions, product/material inclusions, and whether the wedding-day appointment is included. Never imply a package includes a service unless it is explicitly listed.

Groom journey fields:
- Wedding/event date (separate from appointment date/time).
- Which preparation is wanted: one-time grooming / pre-wedding plan / wedding-day finishing.
- Selected package or selected individual services.
- Optional reference photos/style preferences.
- Number of people only if the service is genuinely a group booking.
- Preferred appointment dates for multi-visit plans.
- Address and service location.
- Confirmed appointment slot(s), then a clear review.

## 3. Proposed Women's Beauty experience

### A. Haircut, Hair Wash & Styling
- Women's Haircut
- Hair Trim
- Hair Wash
- Blow Dry
- Hair Styling
- Curls / Straight Styling
- Hair Colour
- Root Touch-up
- Highlights
- Grey Hair Coverage
- Hair Spa
- Keratin Treatment
- Smoothening
- Rebonding / Straightening

Ask for hair length only when it changes price, package, or duration (for example: short / medium / long). For chemical treatments, show hair length, current treatment/colour, relevant allergy or product-reaction notes, and a patch-test acknowledgement where required by salon policy. Reference photos should be optional.

### B. Facial & Skin Care
- Face Cleanup
- Blackhead & Whitehead Removal
- Detan (Face / Neck / selected body area)
- Fruit Facial
- Hydrating Facial
- Brightening Facial
- Charcoal Facial
- Gold Facial
- Pearl Facial
- Diamond Facial
- Bridal Facial
- Face Bleach (only where supported)

Do not present different facial names as if they are different levels of quality unless the actual treatment steps, products, duration, and inclusions are defined. Package tiers should explain what changes between Basic, Deep Cleansing, and Premium.

### C. Waxing & Threading
- Eyebrow Threading
- Upper Lip Threading
- Chin / Forehead / Side Locks
- Full Face Threading
- Threading Combination (select areas)
- Half / Full Arms Waxing
- Half / Full Legs Waxing
- Underarms Waxing
- Full Face Waxing
- Back / Chest Waxing (where offered)
- Bikini Line / Bikini / Brazilian (only with clear scope, trained professionals, privacy/consent controls, and explicit customer selection)

Waxing flow:
1. Select body area(s).
2. Select wax type only if genuinely offered for that area (Regular / Rica / Premium, with plain-language differences).
3. Ask about relevant skin sensitivity, recent skin treatment, or product reaction only when needed.
4. Display coverage, price, duration and any exclusions before confirmation.
5. For intimate-area services, use a separate explicit opt-in and professional capability check; never preselect it or bundle it silently.

### D. Manicure, Pedicure & Nails
- Manicure
- Spa Manicure
- Pedicure
- Spa Pedicure
- Gel Polish
- Nail Art
- Nail Extensions
- Nail Extension Removal / Gel Removal

Ask current nail condition or existing extensions only when it affects the selected service. Show nail-art reference images and clarify whether removal is included.

### E. Makeup & Occasion Styling
- Party Makeup
- Light / Natural Makeup
- HD Makeup
- Engagement Makeup
- Bridal Makeup
- Party Hairstyle
- Bridal Hairstyle
- Saree Draping
- Occasion Hairstyling

For makeup and styling:
- Occasion (party, engagement, wedding, reception, other).
- Event date (not appointment date).
- Preferred look (natural, soft glam, traditional, HD, or not sure).
- Optional reference photos.
- Number of people only for a confirmed group service.
- Trial session only if the business offers it; clearly state whether it is included or separately priced.

### F. Massage & Relaxation
- Head Massage
- Hair Oil Massage
- Hand Massage
- Foot Massage
- Back / Shoulder Massage
- Full Body Spa (only after staff capability, service boundaries, privacy and equipment are verified)

## 4. Both — Unisex services

Only show services intentionally marked as unisex and enabled for both audiences. Candidate services to evaluate include:
- Head Massage
- Hair Wash
- Selected Hair Spa options
- Face Cleanup / selected facials
- Manicure / Pedicure
- Hand / Foot Massage
- Selected back/shoulder massage
- Hair colour or styling only if the actual service is designed and staffed for all customers.

This list is a review shortlist, not automatic approval. Do not place beard services, intimate-area services, bridal makeup, or gender-specific services into Both by default. Some services such as back/chest waxing may be available to multiple audiences only after capability, privacy and scope are confirmed.

## 5. Shared booking flow

For ordinary Beauty services:

**Beauty → Men / Women / Both → service group → service → package/treatment (if applicable) → only relevant questions → professional preference (where applicable) → address → API-confirmed date/time → review → booking confirmation.**

Important:
- Do not ask wedding/event date for an ordinary haircut.
- Do not ask hair length for a threading service.
- Do not ask body-area questions for a facial.
- Do not ask the same preference twice.
- Keep appointment date/time separate from event date.
- Address must be selected before checking slots because service coverage and eligible professionals depend on the address.
- Only show slots confirmed by the backend.
- Show complete price/duration/inclusions before booking; do not use a zero price as a fallback when a package must be selected.
- If no qualified professional is available, explain the actual reason and offer a valid alternative. Never silently substitute a professional who does not meet the selected requirement.

For Beauty professional preference, retain the already agreed choice: **No preference** (default) or **Female professional**. Apply it to eligible-worker and slot matching; do not infer it from Men/Women/Both. A customer who selects Female professional must never be silently switched to another preference.

## 6. Service-specific questions and conditional display

Use configuration-driven questions, not separate hardcoded booking pages for every salon service. Only show questions relevant to the selected service and package.

Examples:
- Haircut → style/length and optional reference photo.
- Beard → trim/shape/shave selection.
- Hair colour → root/full coverage, current colour, hair length if it affects pricing, relevant allergy/patch-test workflow.
- Facial → chosen facial/package and optional skin sensitivity notes.
- Waxing → selected body area, wax type, relevant skin sensitivity.
- Threading → selected areas for combination service.
- Makeup → occasion, event date, style, optional reference photo.
- Groom package → package components, visit plan, wedding date.
- Massage → selected body area and duration.

Changing an upstream answer must clear dependent answers that no longer apply. Backend validation must reject hidden/inapplicable answers and require only visible required answers.

## 7. Consistent photo and image identity rules

A service/category must have one canonical image identity across the entire app.

1. **One source of truth:** use the category/service image returned by the catalogue API. Do not separately hardcode different URLs in Home, category listing, service details, booking, search, and worker screens.
2. **Same service, same photo:** a service card and its service detail page must resolve to the same canonical service image. If a booking/review screen shows the image, it must use that same image.
3. **Same category, same photo:** category tiles, category headers and category shortcuts must use the same category image.
4. **Audience cards:** Men uses a male salon portrait; Women uses a female salon portrait; Both uses a balanced unisex/mixed visual. Keep a consistent premium Indian salon photography style, lighting, crop and image quality.
5. **No misleading images:** do not use a facial image for waxing, a car image for a different vehicle class, or unrelated stock photos just to fill empty spaces.
6. **Fallback order:** verified admin-uploaded image → centrally maintained, reviewed fallback mapping → neutral branded placeholder. Never invent a random image or silently reuse an unrelated image.
7. **No text baked into photography:** labels belong in the UI so the same image can be reused and localized.
8. **Image identity key:** use stable category/service IDs or slugs as the mapping key. Store the canonical image in the backend/admin catalogue; the Flutter app should render the API image.
9. **Quality review:** verify every image against the actual service name and audience before making that service visible.
10. **Accessibility:** add meaningful alt/semantic descriptions where supported and retain readable text labels; customers must not have to identify a service from a photo alone.

## 8. Catalogue and launch safeguards

The existing catalogue snapshot contains several relevant categories and services, but the export showed no service/category images and no approved mapped worker for almost all Beauty services. Existing audience values also need a careful review; an existing value of `all` is not proof that the service is safe, suitable or staffed for all audiences.

Before exposing a service:
- Confirm the service name and customer-facing description.
- Confirm audience: men, women, or both.
- Confirm exact scope, method, package inclusions and exclusions.
- Confirm price, duration, quantity/area rules and any visit/inspection fee.
- Confirm professional skills, tools, products and consumables.
- Confirm any required privacy, consent, hygiene and safety process.
- Confirm worker coverage and real slot availability for the launch area.
- Add and verify the canonical image.
- Test positive, negative, unavailable-worker, invalid-answer, changed-answer and rescheduling scenarios.

Do not change existing prices, activate services, publish unverified packages, or promise service availability as part of this design-only proposal.
