import 'package:flutter/material.dart';
import '../../../core/theme/airway_colors.dart';
import '../../../core/theme/airway_spacing.dart';

/// Terms and Privacy consent screen. Mandatory before account access.
class TermsAndPrivacyScreen extends StatefulWidget {
  const TermsAndPrivacyScreen({super.key});

  @override
  State<TermsAndPrivacyScreen> createState() => _TermsAndPrivacyScreenState();
}

class _TermsAndPrivacyScreenState extends State<TermsAndPrivacyScreen> {
  bool _accepted = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AirwayColors.background,
      appBar: AppBar(
        title: const Text('Terms & Privacy'),
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: ListView(
                padding: AirwaySpacing.screenPadding,
                children: [
                  const Icon(Icons.verified_user_rounded,
                      size: 56, color: AirwayColors.primary),
                  const SizedBox(height: 18),
                  const Text(
                    'Welcome to AIRway',
                    style: TextStyle(
                      fontSize: 26,
                      fontWeight: FontWeight.w800,
                      color: AirwayColors.text,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Please review and accept our terms to continue.',
                    style: TextStyle(
                      fontSize: 15,
                      color: AirwayColors.textSecondary,
                      height: 1.45,
                    ),
                  ),
                  const SizedBox(height: 24),
                  _consentCard(),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
              child: Column(
                children: [
                  _consentToggle(),
                  const SizedBox(height: 12),
                  _acceptButton(context),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _consentCard() => Container(
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: AirwayColors.surface,
          borderRadius: const BorderRadius.all(
            Radius.circular(AirwaySpacing.cardRadius),
          ),
          border: Border.all(color: AirwayColors.border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Terms of Service',
              style: TextStyle(
                fontSize: 17,
                fontWeight: FontWeight.w700,
                color: AirwayColors.text,
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              'By using AIRway you agree to our service terms, booking and '
              'cancellation policy, worker verification standards, and dispute '
              'resolution process.',
              style: TextStyle(
                fontSize: 14,
                height: 1.5,
                color: AirwayColors.textSecondary,
              ),
            ),
            const SizedBox(height: 14),
            const Text(
              'Privacy Policy',
              style: TextStyle(
                fontSize: 17,
                fontWeight: FontWeight.w700,
                color: AirwayColors.text,
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              'We collect the minimum data needed to deliver home services: '
              'your contact details, service address, booking history and '
              'payment records. We never sell your data.',
              style: TextStyle(
                fontSize: 14,
                height: 1.5,
                color: AirwayColors.textSecondary,
              ),
            ),
          ],
        ),
      );

  Widget _consentToggle() => Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: _accepted ? AirwayColors.primarySoft : AirwayColors.surface,
          borderRadius: const BorderRadius.all(
            Radius.circular(AirwaySpacing.chipRadius),
          ),
          border: Border.all(
            color: _accepted ? AirwayColors.primary : AirwayColors.border,
          ),
        ),
        child: Row(
          children: [
            Checkbox(
              value: _accepted,
              onChanged: (value) => setState(() => _accepted = value ?? false),
              activeColor: AirwayColors.primary,
              shape: const ContinuousRectangleBorder(),
              splashRadius: 0,
              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
              visualDensity: const VisualDensity(
                horizontal: -4,
                vertical: -4,
              ),
            ),
            const Expanded(
              child: Text(
                'I have read and accept the Terms of Service and Privacy Policy',
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                  color: AirwayColors.text,
                ),
              ),
            ),
          ],
        ),
      );

  Widget _acceptButton(BuildContext context) => FilledButton(
        onPressed: _accepted
            ? () => Navigator.of(context).pop(true)
            : null,
        child: const Text('Accept and Continue'),
      );
}
