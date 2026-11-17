import 'package:flutter/material.dart';

class LegalDocumentsScreen extends StatelessWidget {
  const LegalDocumentsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Terms & Privacy')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: Colors.amber.withValues(alpha: 0.14),
              borderRadius: BorderRadius.circular(14),
            ),
            child: const Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(Icons.info_outline, color: Colors.orange),
                SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Draft for product review. AIRway’s registered legal entity, business address and verified privacy/support contact must be added and the wording reviewed before this is used as a binding public policy or mandatory consent.',
                    style: TextStyle(fontSize: 12, height: 1.45),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),
          Text('Terms & Conditions', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          const _LegalSection(
            title: 'Using AIRway',
            body: 'AIRway provides a platform to discover and request home and local services. You must provide accurate account, contact and service-address information, keep your sign-in credentials secure, and use the app lawfully. Creating a booking request does not itself guarantee a service slot; a booking is subject to availability, confirmation and the payment conditions shown in the app.',
          ),
          const _LegalSection(
            title: 'Bookings, service and completion',
            body: 'Review the selected service, scope, address, schedule and displayed price before confirming. Changes to the scope may require a revised estimate and your approval. A service is marked complete only after the in-app completion verification process. Raise any issue through the in-app help route as soon as possible.',
          ),
          const _LegalSection(
            title: 'Payments, cancellation and refunds',
            body: 'Payments are processed through the payment options presented at checkout. Your booking and payment status is determined by AIRway’s server records. Cancellation eligibility, applicable charges and refund handling depend on the booking and payment terms shown at the time of the transaction. Do not treat a payment-app success screen alone as confirmation of an AIRway booking.',
          ),
          const _LegalSection(
            title: 'Referral rewards',
            body: 'A valid new customer referral is recorded when the referral code is applied within 24 hours of account creation and before the customer makes a booking. After that referred customer’s first service is successfully completed and verified, AIRway credits ₹200 to the referrer’s wallet and ₹100 to the referred customer’s wallet. Signup, installation, booking, cancellation or an incomplete service does not earn the reward. Each referred customer can be rewarded once.',
          ),
          const _LegalSection(
            title: 'Account restrictions',
            body: 'AIRway may restrict or suspend access where required for security, suspected fraud, misuse, legal compliance or protection of customers and professionals. You may request account closure from Profile. Closure is reviewed against active bookings, disputes, wallet balances and legal record-retention requirements.',
          ),
          const SizedBox(height: 24),
          Text('Privacy Policy', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          const _LegalSection(
            title: 'Information collected',
            body: 'Depending on the features you use, AIRway processes your phone number and authentication details, name, optional email and profile photo, saved addresses and map coordinates, booking and service details, saved vehicle information, ratings, wallet and payment status, device push token, and information you provide in forms. Worker accounts may also submit profile photos and verification documents.',
          ),
          const _LegalSection(
            title: 'How information is used',
            body: 'Information is used to create and secure your account, show services available at your location, create and fulfil bookings, coordinate assigned professionals, process payments and refunds, maintain wallet and referral records, send booking and account notifications, prevent misuse, resolve disputes and meet legal obligations.',
          ),
          const _LegalSection(
            title: 'Sharing and service providers',
            body: 'Relevant booking and address information is shared with the professional assigned to fulfil your service. AIRway uses service providers for functions such as authentication and notifications, address search and payment processing. Payment credentials are handled by the payment provider; AIRway receives transaction identifiers and payment status needed to manage your booking.',
          ),
          const _LegalSection(
            title: 'Location, photos and notifications',
            body: 'Location and address information is used to identify service coverage and fulfil a booking. Photos are used for the account or worker-verification purpose for which they were submitted. Push notifications use your device token and can be controlled in app and device settings; essential in-app booking records remain available in your account.',
          ),
          const _LegalSection(
            title: 'Retention and account closure',
            body: 'AIRway retains booking, payment, refund, wallet, verification and related records for service delivery, dispute handling, security and applicable legal or accounting requirements. An account-closure request does not immediately erase those records. AIRway reviews outstanding obligations before deactivating and anonymising account access data where appropriate.',
          ),
          const _LegalSection(
            title: 'Your choices and contact',
            body: 'You can update profile information, manage saved addresses, control push notifications and submit an account-closure request from the app. A verified privacy contact and registered business details must be published here before public launch; the current Help & Support screen does not yet contain a verified contact channel.',
          ),
        ],
      ),
    );
  }
}

class _LegalSection extends StatelessWidget {
  const _LegalSection({required this.title, required this.body});

  final String title;
  final String body;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
            const SizedBox(height: 5),
            Text(body, style: const TextStyle(height: 1.5)),
          ],
        ),
      );
}
