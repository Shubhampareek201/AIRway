import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_colors.dart';

class HelpSupportScreen extends StatelessWidget {
  final bool workerMode;
  final VoidCallback? onPrimaryAction;
  final VoidCallback? onSecondaryAction;

  const HelpSupportScreen({
    super.key,
    this.workerMode = false,
    this.onPrimaryAction,
    this.onSecondaryAction,
  });

  @override
  Widget build(BuildContext context) {
    final primaryLabel = workerMode ? 'Open jobs' : 'Open my bookings';
    final secondaryLabel = workerMode ? 'View earnings' : 'Open payment options';
    final questions = workerMode
        ? const [
            (
              'Where do new job requests appear?',
              'New requests appear in the Jobs tab and may also arrive as push notifications when enabled. Review the service, time, location and expiry before accepting.',
            ),
            (
              'When are earnings shown?',
              'The Earnings tab displays records returned by AIRway. A recorded earning and a completed bank/UPI payout are not necessarily the same event.',
            ),
            (
              'How do I update my worker details?',
              'Open Profile and use Edit profile details. Changes to verification documents or profile photos may require admin review.',
            ),
            (
              'Why am I not receiving job alerts?',
              'Check that you are online, your service areas and schedule are correct, and push notifications are allowed for AIRway in your phone settings.',
            ),
          ]
        : const [
            (
              'Where can I track a service?',
              'Open My Bookings and select the relevant booking to review its current status and available tracking details.',
            ),
            (
              'Where can I check a payment?',
              'Open the payment options or AIRway Wallet. Payment confirmation is based on the server payment record, not only the payment app screen.',
            ),
            (
              'How do I change my service address?',
              'Open Profile, choose Manage addresses, and add, edit or select a saved address. Confirm the map pin before saving.',
            ),
            (
              'What if a professional has not been assigned yet?',
              'The booking remains visible in My Bookings. Check its current status there; the notification inbox is reserved for meaningful alerts rather than live dispatch progress.',
            ),
          ];

    return Scaffold(
      appBar: AppBar(title: const Text('Help & support')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              color: AirwayColors.primary.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(18),
            ),
            child: Row(
              children: [
                const Icon(Icons.support_agent_rounded, size: 38, color: AirwayColors.primary),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    workerMode
                        ? 'Help with job offers, work profile and earnings'
                        : 'Help with bookings, addresses and payments',
                    style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 18),
          const Text('Common questions', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          for (final item in questions)
            Card(
              child: ExpansionTile(
                title: Text(item.$1, style: const TextStyle(fontWeight: FontWeight.w700)),
                childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                expandedCrossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(item.$2, style: const TextStyle(color: AirwayColors.textSecondary, height: 1.45)),
                ],
              ),
            ),
          const SizedBox(height: 18),
          if (onPrimaryAction != null)
            OutlinedButton.icon(
              onPressed: onPrimaryAction,
              icon: Icon(workerMode ? Icons.work_outline_rounded : Icons.calendar_month_outlined),
              label: Text(primaryLabel),
            ),
          if (onSecondaryAction != null) ...[
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: onSecondaryAction,
              icon: Icon(workerMode ? Icons.account_balance_wallet_outlined : Icons.payments_outlined),
              label: Text(secondaryLabel),
            ),
          ],
          const SizedBox(height: 12),
          const Text(
            'For account-specific or urgent issues, AIRway needs a verified support contact or ticket channel configured by the service team. This screen does not display an unverified phone number or email.',
            style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12, height: 1.45),
          ),
        ],
      ),
    );
  }
}
