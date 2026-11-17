import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:airway/core/network/auth_api.dart';
import 'package:airway/core/storage/secure_session_storage.dart';
import 'package:airway/features/auth/presentation/startup_gate.dart';
import 'package:airway/features/account/presentation/legal_documents_screen.dart';
import 'package:airway/core/localization/airway_text.dart';

class SignupScreen extends StatefulWidget {
  const SignupScreen({super.key});

  @override
  State<SignupScreen> createState() => _SignupScreenState();
}

class _SignupScreenState extends State<SignupScreen> {
  final _nameController = TextEditingController();
  final _phoneController = TextEditingController();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();
  final _referralCodeController = TextEditingController();
  bool _loading = false;
  bool _obscurePassword = true;
  bool _obscureConfirmPassword = true;
  bool _termsAccepted = false;
  bool _privacyAccepted = false;

  @override
  void dispose() {
    _nameController.dispose();
    _phoneController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    _referralCodeController.dispose();
    super.dispose();
  }

  void _message(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _signup() async {
    final name = _nameController.text.trim();
    final phone = _phoneController.text.trim();
    final email = _emailController.text.trim();
    final password = _passwordController.text;
    final confirmPassword = _confirmPasswordController.text;

    if (name.isEmpty) {
      _message(AirwayText.tr('Please enter your full name.', 'कृपया अपना पूरा नाम दर्ज करें।'));
      return;
    }
    if (!RegExp(r'^[6-9]\d{9}$').hasMatch(phone)) {
      _message(AirwayText.tr('Enter a valid 10-digit mobile number.', 'सही 10 अंकों का मोबाइल नंबर दर्ज करें।'));
      return;
    }
    if (email.isNotEmpty && !RegExp(r'^[\w-\.]+@([\w-]+\.)+[\w-]{2,4}$').hasMatch(email)) {
      _message('Enter a valid email address.');
      return;
    }
    if (password.length < 6) {
      _message('Password must be at least 6 characters.');
      return;
    }
    if (password != confirmPassword) {
      _message(AirwayText.tr('Passwords do not match.', 'पासवर्ड मेल नहीं खाते।'));
      return;
    }
    if (!_termsAccepted || !_privacyAccepted) {
      _message(AirwayText.tr('Please accept the Terms & Conditions and Privacy Policy.', 'कृपया नियम और शर्तें तथा गोपनीयता नीति स्वीकार करें।'));
      return;
    }
    if (_loading) return;

    setState(() => _loading = true);

    try {
      final response = await AuthApi.register(
        phone: '+91$phone',
        name: name,
        password: password,
        confirmPassword: confirmPassword,
        email: email.isEmpty ? null : email,
        referralCode: _referralCodeController.text.trim().isEmpty
            ? null
            : _referralCodeController.text.trim(),
        termsAccepted: _termsAccepted,
        privacyAccepted: _privacyAccepted,
      );
      await SecureSessionStorage.saveSession(
        accessToken: response['access'] as String,
        refreshToken: response['refresh'] as String,
      );
      if (!mounted) return;
      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => const StartupGate()),
        (route) => false,
      );
    } on AuthApiException catch (error) {
      if (!mounted) return;
      setState(() => _loading = false);
      _message(error.message);
    } catch (_) {
      if (!mounted) return;
      setState(() => _loading = false);
      _message(AirwayText.tr('Unable to register. Please try again.', 'रजिस्ट्रेशन नहीं हो सका। फिर से कोशिश करें।'));
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = AirwayText.tr;
    const green = Color(0xFF176B58);

    return Scaffold(
      appBar: AppBar(
        title: Text(t('Create Account', 'खाता बनाएँ')),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 10),
              const Text(
                t('Sign Up', 'साइन अप'),
                style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              const Text(
                t('Create your account to get started', 'शुरू करने के लिए अपना खाता बनाएँ'),
                style: TextStyle(fontSize: 16, color: Colors.black54),
              ),
              const SizedBox(height: 32),
              TextField(
                controller: _nameController,
                decoration: InputDecoration(
                  labelText: t('Full Name', 'पूरा नाम'),
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _phoneController,
                keyboardType: TextInputType.phone,
                maxLength: 10,
                inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                decoration: const InputDecoration(
                  labelText: t('Mobile Number', 'मोबाइल नंबर'),
                  prefixText: '+91 ',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _emailController,
                keyboardType: TextInputType.emailAddress,
                decoration: const InputDecoration(
                  labelText: t('Email (Optional)', 'ईमेल (वैकल्पिक)'),
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _referralCodeController,
                textCapitalization: TextCapitalization.characters,
                inputFormatters: [FilteringTextInputFormatter.allow(RegExp('[A-Za-z0-9]'))],
                decoration: const InputDecoration(
                  labelText: t('Referral Code (Optional)', 'रेफ़रल कोड (वैकल्पिक)'),
                  helperText: t('Enter your friend’s code to receive ₹100 after your first completed service.', 'पहली सेवा पूरी होने पर ₹100 पाने के लिए दोस्त का कोड दर्ज करें।'),
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _passwordController,
                obscureText: _obscurePassword,
                decoration: InputDecoration(
                  labelText: t('Password', 'पासवर्ड'),
                  border: const OutlineInputBorder(),
                  suffixIcon: IconButton(
                    icon: Icon(_obscurePassword ? Icons.visibility_off : Icons.visibility),
                    onPressed: () {
                      setState(() => _obscurePassword = !_obscurePassword);
                    },
                  ),
                ),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _confirmPasswordController,
                obscureText: _obscureConfirmPassword,
                decoration: InputDecoration(
                  labelText: t('Confirm Password', 'पासवर्ड की पुष्टि करें'),
                  border: const OutlineInputBorder(),
                  suffixIcon: IconButton(
                    icon: Icon(_obscureConfirmPassword ? Icons.visibility_off : Icons.visibility),
                    onPressed: () {
                      setState(() => _obscureConfirmPassword = !_obscureConfirmPassword);
                    },
                  ),
                ),
              ),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                value: _termsAccepted,
                onChanged: _loading ? null : (value) => setState(() => _termsAccepted = value ?? false),
                controlAffinity: ListTileControlAffinity.leading,
                title: Text(t('I agree to the Terms & Conditions', 'मैं नियम और शर्तों से सहमत हूँ')),
              ),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                value: _privacyAccepted,
                onChanged: _loading ? null : (value) => setState(() => _privacyAccepted = value ?? false),
                controlAffinity: ListTileControlAffinity.leading,
                title: const Text(t('I have read and agree to the Privacy Policy', 'मैंने गोपनीयता नीति पढ़ ली है और सहमत हूँ')),
              ),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton(
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute(builder: (_) => const LegalDocumentsScreen()),
                  ),
                  child: Text(t('Read Terms & Privacy', 'नियम और गोपनीयता पढ़ें')),
                ),
              ),
              const SizedBox(height: 24),
              SizedBox(
                width: double.infinity,
                height: 54,
                child: FilledButton(
                  style: FilledButton.styleFrom(backgroundColor: green),
                  onPressed: _loading ? null : _signup,
                  child: _loading
                      ? const SizedBox(
                          width: 22,
                          height: 22,
                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                        )
                      : const Text(t('Sign Up', 'साइन अप')),
                ),
              ),
              const SizedBox(height: 16),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Text("Already have an account? "),
                  TextButton(
                    onPressed: () {
                      Navigator.of(context).pop();
                    },
                    child: const Text(t('Login', 'लॉगिन')),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
