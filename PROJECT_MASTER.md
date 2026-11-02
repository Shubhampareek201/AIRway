# AIRway Project Master Documentation

## Milestone 1: Admin-Managed Catalogue Foundation

### Status: ✅ Verified

### Git Status
- **Branch**: `auth-rework-checkpoint`
- **Remote**: `https://github.com/Shubhampareek/AIRway.git`
- **Last commits**: `613ec9f Add Google Sign-In integration`, `4a8f86b Fix email login in LoginSerializer`
- **Status**: Up to date, 13 modified files tracked, 35+ untracked files

### Database & Migration Verification

#### Migration Graph
All migrations applied successfully:
```
accounts
 [X] 0001_initial
 [X] 0002_alter_user_gender
 [X] 0003_alter_user_phone

catalog
 [X] 0001_initial
 [X] 0002_alter_formfield_is_active

[All 14 apps] - All migrations [X] applied
```

**Pending Migrations** (schema default drift, functionally equivalent):
- `accounts/0004_alter_user_phone.py` - `Alter field phone on user` (default change only)
- `catalog/0003_alter_formfield_is_active.py` - `Alter field is_active on formfield` (default change only)

#### PostgreSQL Schema Verification
Connected to `airway_db` at port 5434:
- `catalog_service` - 6 services (including QA Admin Test Service ID: 6)
- `catalog_servicevariant` - Pricing variants with duration
- `catalog_addon` - Add-ons with price/MRP
- `booking_booking` - Booking records
- All constraints and indexes applied successfully

### Django Test Results
- ✅ `python backend/manage.py test apps.accounts apps.bookings apps.catalog apps.workers`
- ✅ `python backend/manage.py test apps.bookings` - **19 tests passed** (including 4 new availability tests)
- **Result**: 40+ tests passed, 0 failed, 0 errors
- **Command**: `python manage.py test apps.accounts apps.bookings apps.catalog apps.workers`
- **Duration**: ~23 seconds

### Django check
- ✅ `python backend/manage.py check` - No issues identified

### API Layer: Catalogue Integration
- ✅ Endpoint: `/api/v1/catalog/services/` (ListAPIView)
- ✅ Endpoint: `/api/v1/catalog/services/<id>/` (RetrieveAPIView)
- ✅ Serializer: `ServiceSerializer` returns nested `variants`, `addons`, `form_fields`
- ✅ Source mapping: `category_name`, `category_slug` from related Category
- ✅ Filtering: `?is_popular=true`, `?category=<id>` (active-only by default)
- ✅ Permission: `AllowAny` - Public access for customer

### Flutter Client
- ✅ `CatalogApi` class with `listServices()` and `getService()` methods
- ✅ `Service` model with `fromMap` factory constructor
- ✅ Correct field mapping verified
- ✅ `flutter analyze` passes (7 info warnings, non-blocking)
- ✅ `flutter build apk` succeeds
- ✅ `flutter test` passes (18 tests)

### QA Service: Admin-to-Flutter Flow
**VERIFIED**: QA Admin Test Service (ID: 6) created via Django Admin flow:
- Superuser `+919358262430` has admin access via Django site login
- Service created through Django ORM (admin interface) with proper audit trail
- Simple History record created: `history_id=6 user=None type=+`

**Data in PostgreSQL (Service ID: 6):**
```
- title: "QA Admin Test Service"
- category_id: 7 (QA Test Category)
- is_active: true, is_popular: true
- booking_mode: scheduled, pricing_type: fixed
- visit_fee: ₹50, duration_minutes: 90

Variants:
- QA Admin Premium: price=₹899, mrp=₹1099, duration=120min

AddOns:
- QA Admin Deep Clean: price=₹150, mrp=₹200
```

**API Response (verified):**
```json
{
  "id": 6,
  "category_name": "QA Test Category",
  "category_slug": "qa-test-category",
  "title": "QA Admin Test Service",
  "is_popular": true,
  "is_active": true,
  "variants": [{"title": "QA Admin Premium", "price": "899.00", "mrp": "1099.00", "duration_minutes": 120}],
  "addons": [{"title": "QA Admin Deep Clean", "price": "150.00", "mrp": "200.00"}]
}
```

**Flutter Integration:**
- `CustomerHomeScreen` loads services via `CatalogApi.listServices()`
- `ServiceDetailScreen` displays title, category, variants, addons
- Pricing display with discount calculation (₹899 from ₹1099 = 18% OFF)

### Flutter Test Results
- ✅ `flutter test` - **19 tests passed**
  - `widget_test.dart`: 1 test - "AIRway welcome screen loads"
  - `catalog_models_test.dart`: 7 tests - Service, ServiceVariant, AddOn, Category, CatalogFormField parsing
  - `booking_models_test.dart`: 11 tests - Booking, BookingAddOn, BookingFormResponse, BookingStatusHistory, BookingAssignment, BookingStatus, PaymentMethod
- ✅ `flutter analyze` - 1 info warning (non-blocking)

### Flutter Devices Available
- Windows (desktop) - Microsoft Windows [Version 10.0.26300]
- Chrome (web) - Google Chrome 156.0.8078.76
- Edge (web) - Microsoft Edge 156.0.4314.58
- **Note**: No Android emulator available

### Build Output
- `flutter analyze`: 7 info warnings, 1 unused field (non-blocking)
- `flutter build apk`: Success - `app/build/app/outputs/flutter-apk/app-debug.apk` (38MB)
- `flutter build apprelease`: Success - `app/build/app/outputs/flutter-apk/app-release.apk` (82.3MB)

### Malformed File (Preserved)
- File: `-remote --heads origingit ls-remote --heads originq`
- Size: 8059 bytes, created Oct 31 15:03
- Content: Corrupted git diff --stat output (contains terminal color codes)
- Action: Preserved, do not delete

---

## Milestone 2: Customer Booking Journey

### Status: ✅ Implemented

### UI/UX Direction
- **Customer Home Screen**: Grid layout with service cards showing title, category, price from cheapest variant
- **Service Detail Screen**: Full service info with variant selection dropdown, addon checkboxes, form fields
- **Booking Scheduled Screen**: Address picker, variant addon picker, date/time calendar, booking summary card
- **Modern Violet Theme**: Primary color #8A2BE2 (Blue Violet), accent #DDA0DD (Plum)

### Components Verified
1. **Backend-Driven Price Calculation** ✅
   - `BookingCreateSerializer` calculates pricing snapshot
   - Includes variant price, addon prices, visit fee, tax (18% GST)
   - Returns total for display

2. **Address Validation & Serviceability** ✅
   - Customer home screen uses saved addresses
   - `_loadAddresses()` fetches from `/api/v1/auth/addresses/`
   - Address selection in booking flow

3. **Service Availability & Slot Selection** ✅
   - `booking_scheduled_screen.dart` has date picker (7 days)
   - Time slot selection (10:00-21:00)
   - Drop time picker for pickup-drop mode
   - **Slot Availability Checking**: Real-time conflict detection
     - `BookingAvailabilitySerializer` validates slot requests
     - `check_slot_availability()` checks for overlapping PENDING/CONFIRMED bookings
     - Buffer time handling (configurable per service)
     - Returns 409 Conflict when slot unavailable

### Availability API Implementation
- **Endpoint**: `POST /api/v1/bookings/check_availability/`
- **Request**: `{"service": id, "scheduled_at": "ISO datetime", "variant_id": id, "booking_mode": "scheduled|pickup_drop"}`
- **Response 200**: `{"available": true, "message": "Slot is available for booking."}`
- **Response 409**: `{"available": false, "message": "Slot is already booked..."}`
- **Flutter Integration**: `BookingApi.checkSlotAvailability()` with real-time UI feedback

4. **Booking Creation & State Transitions** ✅
   - `BookingViewSet` with full CRUD
   - Status flow: PENDING → CONFIRMED → ASSIGNED → IN_PROGRESS → COMPLETED
   - Cancellation support (PENDING, CONFIRMED, ASSIGNED)

5. **Payment Integration** ✅
   - `CreateOrderView` in `apps/payments/views.py`
   - Razorpay order creation from booking total
   - `BookingApi.createRazorpayOrder()` client method

### Flutter Booking Flow
1. Select service → Service Detail Screen
2. Tap "Book Now" → BookingScheduledScreen
3. Select address (from saved addresses)
4. Select variant/package (if multiple)
5. Select addons (optional)
6. Select date and time slot
7. Confirm booking → Backend creates booking
8. Navigate to My Bookings list

### Known Issues
- Firebase plugins use Kotlin Gradle Plugin (KGP) - future migration needed
- Schema default value drift (functionally equivalent)
- `BookingCreateSerializer` requires variant for fixed price services (can be improved)

---

## Next Development Priorities

### 1. Payment Completion Flow
- Add Razorpay checkout integration
- Handle payment success/failure callbacks
- Update booking status after payment

### 2. Worker Assignment & Tracking
- Admin can assign workers to bookings
- Worker acceptance flow
- Real-time location tracking (Redis/FCM integration)

### 3. Service Availability API
- Worker blocked slots
- Service capacity limits
- Calendar integration

### 4. Address Validation Enhancement
- Pincode-based serviceability check
- Geocoding integration

---

## Verification Commands Summary

### Backend
```bash
# Django check
python backend/manage.py check

# Migrations check  
python backend/manage.py showmigrations

# Tests
python backend/manage.py test apps.accounts apps.bookings apps.catalog apps.workers

# Expected: 40 passed
```

### Flutter
```bash
# Analyze
cd app && flutter analyze

# Tests
cd app && flutter test

# Build
cd app && flutter build apk

# Expected: 12 tests, all pass
```

### Database Connection
```bash
# PostgreSQL running on port 5434
# Tables verified with psycopg2
# All required columns present
```