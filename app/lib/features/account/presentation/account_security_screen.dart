import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/auth/presentation/forgot_password_screen.dart';
import 'package:airway/features/account/data/account_api.dart';
import 'package:airway/features/location/data/location_api.dart';

class AccountSecurityScreen extends StatefulWidget {
  const AccountSecurityScreen({super.key});

  @override
  State<AccountSecurityScreen> createState() => _AccountSecurityScreenState();
}

class _AccountSecurityScreenState extends State<AccountSecurityScreen> {
  final _oldPassword = TextEditingController();
  final _newPassword = TextEditingController();
  final _confirmPassword = TextEditingController();
  bool _hasPassword = false;
  bool _loading = true;
  bool _saving = false;
  bool _obscureOld = true;
  bool _obscureNew = true;
  bool _obscureConfirm = true;
  String? _phone;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _oldPassword.dispose();
    _newPassword.dispose();
    _confirmPassword.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final profile = await AccountApi.fetchProfile();
      if (!mounted) return;
      setState(() {
        _hasPassword = profile['has_usable_password'] == true;
        _phone = profile['phone']?.toString();
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loading = false);
      _message('Could not load account security details.');
    }
  }

  Future<void> _changePassword() async {
    if (_saving) return;
    final oldPassword = _oldPassword.text;
    final newPassword = _newPassword.text;
    final confirm = _confirmPassword.text;
    if (oldPassword.isEmpty || newPassword.isEmpty || confirm.isEmpty) {
      _message('Complete all password fields.');
      return;
    }
    if (newPassword != confirm) {
      _message('New passwords do not match.');
      return;
    }
    if (newPassword == oldPassword) {
      _message('Choose a password different from your current password.');
      return;
    }

    setState(() => _saving = true);
    try {
      await LocationApi.request(
        '/api/v1/auth/change-password/',
        method: 'POST',
        data: {
          'old_password': oldPassword,
          'new_password': newPassword,
          'confirm_new_password': confirm,
        },
      );
      if (!mounted) return;
      _oldPassword.clear();
      _newPassword.clear();
      _confirmPassword.clear();
      _message('Password changed successfully.');
    } catch (error) {
      if (!mounted) return;
      _message(error.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  void _message(String value) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(value)));
  }

  Widget _passwordField(
    String label,
    TextEditingController controller,
    bool obscure,
    VoidCallback toggle, {
    bool current = false,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: TextFormField(
        controller: controller,
        obscureText: obscure,
        enabled: !_saving,
        autofillHints: current
            ? const [AutofillHints.password]
            : const [AutofillHints.newPassword],
        decoration: InputDecoration(
          labelText: label,
          prefixIcon: const Icon(Icons.lock_outline_rounded),
          suffixIcon: IconButton(
            onPressed: toggle,
            icon: Icon(obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Password & security')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : !_hasPassword
              ? ListView(
                  padding: const EdgeInsets.all(20),
                  children: [
                    const Icon(Icons.verified_user_outlined, size: 54, color: AirwayColors.primary),
                    const SizedBox(height: 16),
                    const Text(
                      'Your account uses OTP or Google sign-in',
                      style: TextStyle(fontSize: 19, fontWeight: FontWeight.w800),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'No password is currently set for ${_phone ?? 'this account'}. You can create or reset one using OTP verification.',
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: AirwayColors.textSecondary, height: 1.45),
                    ),
                    const SizedBox(height: 20),
                    if (_phone?.isNotEmpty == true)
                      FilledButton(
                        onPressed: () async {
                          await Navigator.of(context).push(
                            MaterialPageRoute(builder: (_) => const ForgotPasswordScreen()),
                          );
                          if (mounted) await _load();
                        },
                        child: const Text('Set password with OTP'),
                      )
                    else
                      const Text(
                        'No phone number is linked to this account. Continue with Google sign-in; adding a phone number requires a separate verification flow.',
                        textAlign: TextAlign.center,
                        style: TextStyle(color: AirwayColors.textSecondary, height: 1.45),
                      ),
                  ],
                )
              : ListView(
                  padding: const EdgeInsets.all(20),
                  children: [
                    const Text(
                      'Change your password',
                      style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'Use a strong password you do not use on other websites.',
                      style: TextStyle(color: AirwayColors.textSecondary),
                    ),
                    const SizedBox(height: 22),
                    _passwordField('Current password', _oldPassword, _obscureOld,
                        () => setState(() => _obscureOld = !_obscureOld), current: true),
                    _passwordField('New password', _newPassword, _obscureNew,
                        () => setState(() => _obscureNew = !_obscureNew)),
                    _passwordField('Confirm new password', _confirmPassword, _obscureConfirm,
                        () => setState(() => _obscureConfirm = !_obscureConfirm)),
                    const SizedBox(height: 8),
                    FilledButton(
                      onPressed: _saving ? null : _changePassword,
                      child: _saving
                          ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                          : const Text('Update password'),
                    ),
                  ],
                ),
    );
  }
}
