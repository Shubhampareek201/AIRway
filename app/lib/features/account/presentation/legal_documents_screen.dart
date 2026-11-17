import 'package:flutter/material.dart';
import 'package:airway/core/localization/airway_text.dart';

class LegalDocumentsScreen extends StatelessWidget {
  const LegalDocumentsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final t = AirwayText.tr;
    return Scaffold(
      appBar: AppBar(title: Text(t('Terms & Privacy', 'नियम और गोपनीयता'))),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: Colors.amber.withValues(alpha: 0.14),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.info_outline, color: Colors.orange),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    t(
                      'Draft for product review. AIRway’s registered legal entity, business address and verified privacy/support contact must be added and the wording reviewed before this is used as a binding public policy or mandatory consent.',
                      'उत्पाद समीक्षा के लिए प्रारूप। इसे बाध्यकारी सार्वजनिक नीति या अनिवार्य सहमति के रूप में उपयोग करने से पहले AIRway की पंजीकृत कानूनी इकाई, व्यावसायिक पता और सत्यापित गोपनीयता/सहायता संपर्क जोड़ना तथा कानूनी समीक्षा कराना आवश्यक है।',
                    ),
                    style: const TextStyle(fontSize: 12, height: 1.45),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),
          Text(t('Terms & Conditions', 'नियम और शर्तें'), style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          _LegalSection(
            title: t('Using AIRway', 'AIRway का उपयोग'),
            body: t(
              'AIRway provides a platform to discover and request home and local services. You must provide accurate account, contact and service-address information, keep your sign-in credentials secure, and use the app lawfully. Creating a booking request does not itself guarantee a service slot; a booking is subject to availability, confirmation and the payment conditions shown in the app.',
              'AIRway घर और स्थानीय सेवाओं को खोजने और अनुरोध करने का प्लेटफ़ॉर्म है। आपको सही खाता, संपर्क और सेवा-पते की जानकारी देनी होगी, लॉगिन विवरण सुरक्षित रखने होंगे और ऐप का वैध उपयोग करना होगा। बुकिंग अनुरोध करने से स्लॉट की गारंटी नहीं मिलती; बुकिंग उपलब्धता, पुष्टि और ऐप में दिखाए गए भुगतान नियमों के अधीन है।',
            ),
          ),
          _LegalSection(
            title: t('Bookings, service and completion', 'बुकिंग, सेवा और पूर्णता'),
            body: t(
              'Review the selected service, scope, address, schedule and displayed price before confirming. Changes to the scope may require a revised estimate and your approval. A service is marked complete only after the in-app completion verification process. Raise any issue through the in-app help route as soon as possible.',
              'पुष्टि करने से पहले चुनी गई सेवा, कार्य-सीमा, पता, समय और दिखाई गई कीमत जाँचें। कार्य-सीमा में बदलाव के लिए नया अनुमान और आपकी स्वीकृति आवश्यक हो सकती है। ऐप में पूर्णता सत्यापन के बाद ही सेवा पूरी मानी जाएगी। किसी समस्या की सूचना जल्द से जल्द ऐप की सहायता सुविधा से दें।',
            ),
          ),
          _LegalSection(
            title: t('Payments, cancellation and refunds', 'भुगतान, रद्दीकरण और रिफंड'),
            body: t(
              'Payments are processed through the payment options presented at checkout. Your booking and payment status is determined by AIRway’s server records. Cancellation eligibility, applicable charges and refund handling depend on the booking and payment terms shown at the time of the transaction. Do not treat a payment-app success screen alone as confirmation of an AIRway booking.',
              'भुगतान चेकआउट में उपलब्ध विकल्पों के माध्यम से संसाधित होते हैं। बुकिंग और भुगतान की स्थिति AIRway के सर्वर रिकॉर्ड से तय होती है। रद्दीकरण की पात्रता, शुल्क और रिफंड उस समय दिखाए गए बुकिंग और भुगतान नियमों पर निर्भर करते हैं। केवल भुगतान ऐप की सफलता स्क्रीन को AIRway बुकिंग की पुष्टि न मानें।',
            ),
          ),
          _LegalSection(
            title: t('Referral rewards', 'रेफ़रल पुरस्कार'),
            body: t(
              'A valid new customer referral is recorded when the referral code is applied within 24 hours of account creation and before the customer makes a booking. After that referred customer’s first service is successfully completed and verified, AIRway credits ₹200 to the referrer’s wallet and ₹100 to the referred customer’s wallet. Signup, installation, booking, cancellation or an incomplete service does not earn the reward. Each referred customer can be rewarded once.',
              'नए ग्राहक का रेफ़रल तभी मान्य होगा जब खाता बनने के 24 घंटे के भीतर और पहली बुकिंग से पहले रेफ़रल कोड लागू किया जाए। उस ग्राहक की पहली सेवा सफलतापूर्वक पूरी और सत्यापित होने पर रेफ़र करने वाले के वॉलेट में ₹200 और नए ग्राहक के वॉलेट में ₹100 जमा होंगे। केवल ऐप इंस्टॉल, साइनअप, बुकिंग, रद्दीकरण या अधूरी सेवा पर पुरस्कार नहीं मिलेगा। प्रत्येक नए ग्राहक पर एक बार ही पुरस्कार मिलेगा।',
            ),
          ),
          _LegalSection(
            title: t('Account restrictions', 'खाते पर प्रतिबंध'),
            body: t(
              'AIRway may restrict or suspend access where required for security, suspected fraud, misuse, legal compliance or protection of customers and professionals. You may request account closure from Profile. Closure is reviewed against active bookings, disputes, wallet balances and legal record-retention requirements.',
              'सुरक्षा, संभावित धोखाधड़ी, दुरुपयोग, कानूनी अनुपालन या ग्राहकों और सेवा प्रदाताओं की सुरक्षा के लिए AIRway पहुँच सीमित या निलंबित कर सकता है। आप प्रोफ़ाइल से खाता बंद करने का अनुरोध कर सकते हैं। अनुरोध की समीक्षा सक्रिय बुकिंग, विवाद, वॉलेट बैलेंस और कानूनी रिकॉर्ड रखने की आवश्यकताओं के आधार पर होगी।',
            ),
          ),
          const SizedBox(height: 24),
          Text(t('Privacy Policy', 'गोपनीयता नीति'), style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          _LegalSection(
            title: t('Information collected', 'एकत्र की जाने वाली जानकारी'),
            body: t(
              'Depending on the features you use, AIRway processes your phone number and authentication details, name, optional email and profile photo, saved addresses and map coordinates, booking and service details, saved vehicle information, ratings, wallet and payment status, device push token, and information you provide in forms. Worker accounts may also submit profile photos and verification documents.',
              'आपके उपयोग किए गए फ़ीचर्स के अनुसार AIRway आपका फ़ोन नंबर और प्रमाणीकरण विवरण, नाम, वैकल्पिक ईमेल और प्रोफ़ाइल फोटो, सहेजे गए पते और मैप निर्देशांक, बुकिंग और सेवा विवरण, वाहन जानकारी, रेटिंग, वॉलेट और भुगतान स्थिति, डिवाइस पुश टोकन तथा फ़ॉर्म में दी गई जानकारी संसाधित कर सकता है। वर्कर खाते प्रोफ़ाइल फोटो और सत्यापन दस्तावेज़ भी जमा कर सकते हैं।',
            ),
          ),
          _LegalSection(
            title: t('How information is used', 'जानकारी का उपयोग'),
            body: t(
              'Information is used to create and secure your account, show services available at your location, create and fulfil bookings, coordinate assigned professionals, process payments and refunds, maintain wallet and referral records, send booking and account notifications, prevent misuse, resolve disputes and meet legal obligations.',
              'जानकारी का उपयोग खाता बनाने और सुरक्षित रखने, आपके क्षेत्र में उपलब्ध सेवाएँ दिखाने, बुकिंग बनाने और पूरी कराने, सेवा प्रदाताओं से समन्वय, भुगतान और रिफंड संसाधित करने, वॉलेट और रेफ़रल रिकॉर्ड रखने, सूचनाएँ भेजने, दुरुपयोग रोकने, विवाद सुलझाने और कानूनी दायित्व पूरे करने के लिए किया जाता है।',
            ),
          ),
          _LegalSection(
            title: t('Sharing and service providers', 'जानकारी साझा करना और सेवा प्रदाता'),
            body: t(
              'Relevant booking and address information is shared with the professional assigned to fulfil your service. AIRway uses service providers for functions such as authentication and notifications, address search and payment processing. Payment credentials are handled by the payment provider; AIRway receives transaction identifiers and payment status needed to manage your booking.',
              'आपकी सेवा के लिए नियुक्त पेशेवर के साथ संबंधित बुकिंग और पता जानकारी साझा की जाती है। AIRway प्रमाणीकरण, सूचनाओं, पता खोज और भुगतान संसाधित करने के लिए सेवा प्रदाताओं का उपयोग करता है। भुगतान विवरण भुगतान प्रदाता संभालता है; AIRway को बुकिंग प्रबंधन के लिए आवश्यक लेन-देन पहचान और भुगतान स्थिति मिलती है।',
            ),
          ),
          _LegalSection(
            title: t('Location, photos and notifications', 'लोकेशन, फोटो और सूचनाएँ'),
            body: t(
              'Location and address information is used to identify service coverage and fulfil a booking. Photos are used for the account or worker-verification purpose for which they were submitted. Push notifications use your device token and can be controlled in app and device settings; essential in-app booking records remain available in your account.',
              'लोकेशन और पते की जानकारी सेवा उपलब्धता जाँचने और बुकिंग पूरी करने के लिए उपयोग होती है। फोटो उसी खाते या वर्कर सत्यापन उद्देश्य के लिए उपयोग की जाती हैं जिसके लिए वे जमा की गई थीं। पुश नोटिफिकेशन आपके डिवाइस टोकन का उपयोग करते हैं और ऐप तथा डिवाइस सेटिंग से नियंत्रित किए जा सकते हैं; आवश्यक बुकिंग रिकॉर्ड खाते में उपलब्ध रहते हैं।',
            ),
          ),
          _LegalSection(
            title: t('Retention and account closure', 'जानकारी रखना और खाता बंद करना'),
            body: t(
              'AIRway retains booking, payment, refund, wallet, verification and related records for service delivery, dispute handling, security and applicable legal or accounting requirements. An account-closure request does not immediately erase those records. AIRway reviews outstanding obligations before deactivating and anonymising account access data where appropriate.',
              'सेवा, विवाद समाधान, सुरक्षा और लागू कानूनी या लेखा आवश्यकताओं के लिए AIRway बुकिंग, भुगतान, रिफंड, वॉलेट, सत्यापन और संबंधित रिकॉर्ड रखता है। खाता बंद करने का अनुरोध इन रिकॉर्ड को तुरंत नहीं मिटाता। जहाँ उचित हो, खाते की पहुँच निष्क्रिय और व्यक्तिगत पहचान वाली जानकारी अनाम करने से पहले लंबित दायित्वों की समीक्षा की जाती है।',
            ),
          ),
          _LegalSection(
            title: t('Your choices and contact', 'आपके विकल्प और संपर्क'),
            body: t(
              'You can update profile information, manage saved addresses, control push notifications and submit an account-closure request from the app. A verified privacy contact and registered business details must be published here before public launch; the current Help & Support screen does not yet contain a verified contact channel.',
              'आप ऐप से प्रोफ़ाइल जानकारी अपडेट कर सकते हैं, पते प्रबंधित कर सकते हैं, पुश नोटिफिकेशन नियंत्रित कर सकते हैं और खाता बंद करने का अनुरोध भेज सकते हैं। सार्वजनिक लॉन्च से पहले यहाँ सत्यापित गोपनीयता संपर्क और पंजीकृत व्यावसायिक विवरण प्रकाशित करना आवश्यक है; मौजूदा Help & Support स्क्रीन में अभी सत्यापित संपर्क चैनल नहीं है।',
            ),
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
