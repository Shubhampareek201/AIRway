import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_colors.dart';

class PaymentOptionsScreen extends StatelessWidget {
  const PaymentOptionsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Payment options')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: ListTile(
              leading: const CircleAvatar(
                backgroundColor: Color(0xFFEAF1EA),
                child: Icon(Icons.account_balance_wallet_outlined, color: AirwayColors.primary),
              ),
              title: const Text('AIRway Wallet', style: TextStyle(fontWeight: FontWeight.w700)),
              subtitle: const Text('Use your available wallet balance during eligible checkout flows.'),
            ),
          ),
          Card(
            child: ListTile(
              leading: const CircleAvatar(
                backgroundColor: Color(0xFFEAF1EA),
                child: Icon(Icons.payments_outlined, color: AirwayColors.primary),
              ),
              title: const Text('Online payment', style: TextStyle(fontWeight: FontWeight.w700)),
              subtitle: const Text('Online checkout is securely processed through Razorpay. Available options are shown at payment time.'),
            ),
          ),
          const SizedBox(height: 12),
          const ListTile(
            leading: Icon(Icons.shield_outlined, color: AirwayColors.primary),
            title: Text('Payment security'),
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
