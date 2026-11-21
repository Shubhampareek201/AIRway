import 'package:flutter/material.dart';
import 'package:airway/core/localization/airway_text.dart';
import 'package:airway/core/theme/airway_colors.dart';

class PaymentOptionsScreen extends StatelessWidget {
  const PaymentOptionsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(AirwayText.tr('Payment options', 'भुगतान विकल्प'))),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: ListTile(
              leading: const CircleAvatar(
                backgroundColor: Color(0xFFEAF1EA),
                child: Icon(Icons.account_balance_wallet_outlined, color: AirwayColors.primary),
              ),
              title: Text(AirwayText.tr('AIRway Wallet', 'AIRway वॉलेट'), style: TextStyle(fontWeight: FontWeight.w700)),
              subtitle: Text(AirwayText.tr('Use your available wallet balance during eligible checkout flows.', 'योग्य चेकआउट के दौरान अपने उपलब्ध वॉलेट बैलेंस का उपयोग करें।')),
            ),
          ),
          Card(
            child: ListTile(
              leading: const CircleAvatar(
                backgroundColor: Color(0xFFEAF1EA),
                child: Icon(Icons.payments_outlined, color: AirwayColors.primary),
              ),
              title: Text(AirwayText.tr('Online payment', 'ऑनलाइन भुगतान'), style: TextStyle(fontWeight: FontWeight.w700)),
              subtitle: Text(AirwayText.tr('Online checkout is securely processed through Razorpay. Available options are shown at payment time.', 'ऑनलाइन भुगतान Razorpay के माध्यम से सुरक्षित रूप से किया जाता है। उपलब्ध विकल्प भुगतान के समय दिखेंगे।')),
            ),
          ),
          const SizedBox(height: 12),
          const ListTile(
            leading: Icon(Icons.shield_outlined, color: AirwayColors.primary),
            title: Text(AirwayText.tr('Payment security', 'भुगतान सुरक्षा')),
            subtitle: Text(
              'AIRway does not display or store your full card details here. Payment credentials are handled by the payment provider.',
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            'Saved cards and reusable payment mandates are not currently managed from the AIRway account screen. Choose an available method during checkout.',
            style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12, height: 1.45),
          ),
        ],
      ),
    );
  }
}
