import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:airway/core/network/auth_api.dart';
import 'package:airway/features/auth/presentation/reset_password_screen.dart';

class ForgotPasswordScreen extends StatefulWidget {
  const ForgotPasswordScreen({super.key});

  @override
  State<ForgotPasswordScreen> createState() => _ForgotPasswordScreenState();
}

class _ForgotPasswordScreenState extends State<ForgotPasswordScreen> {
  final _phoneController = TextEditingController();
  bool _loading = false;

  @override
  void dispose() {
    _phoneController.dispose();
    super.dispose();
  }

  void _message(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _sendOtp() async {
    final phone = _phoneController.text.trim();
    if (!RegExp(r'^[6-9]\d{9}$').hasMatch(phone)) {
      _message('Enter a valid 10-digit mobile number.');
      return;
    }
    if (_loading) return;

    setState(() => _loading = true);

    try {
      final response = await AuthApi.forgotPassword(phone: '+91$phone');
      if (!mounted) return;
      setState(() => _loading = false);
      _message(response['message'] ?? 'OTP sent successfully');
      Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => ResetPasswordScreen(phone: '+91$phone')),
      );
    } on AuthApiException catch (error) {
      if (!mounted) return;
      setState(() => _loading = false);
      _message(error.message);
    } catch (_) {
      if (!mounted) return;
      setState(() => _loading = false);
      _message('Unable to send OTP. Please try again.');
    }
  }

  @override
  Widget build(BuildContext context) {
    const green = Color(0xFF176B58);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Forgot Password'),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 20),
              const Text(
                'Reset Password',
                style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              const Text(
                'Enter your registered mobile number to receive OTP',
                style: TextStyle(fontSize: 16, color: Colors.black54),
              ),
              const SizedBox(height: 32),
              TextField(
                controller: _phoneController,
                keyboardType: TextInputType.phone,
                maxLength: 10,
                inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                decoration: const InputDecoration(
                  labelText: 'Mobile Number',
                  prefixText: '+91 ',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 24),
              SizedBox(
                width: double.infinity,
                height: 54,
                child: FilledButton(
                  style: FilledButton.styleFrom(backgroundColor: green),
                  onPressed: _loading ? null : _sendOtp,
                  child: _loading
                      ? const SizedBox(
                          width: 22,
                          height: 22,
                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                        )
                      : const Text('Send OTP'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
