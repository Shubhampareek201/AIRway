
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:airway/features/auth/presentation/startup_gate.dart';
import 'package:flutter/services.dart';
import 'package:airway/core/network/auth_api.dart';
import 'package:airway/core/storage/secure_session_storage.dart';
class PhoneLoginScreen extends StatefulWidget {
  const PhoneLoginScreen({super.key});

  @override
  State<PhoneLoginScreen> createState() => _PhoneLoginScreenState();
}

class _PhoneLoginScreenState extends State<PhoneLoginScreen> {
  final _phoneController = TextEditingController();
  final _otpController = TextEditingController();
  final _auth = FirebaseAuth.instance;

  bool _loading = false;
  bool _otpSent = false;
  bool _verified = false;
  String? _verificationId;

  @override
  void dispose() {
    _phoneController.dispose();
    _otpController.dispose();
    super.dispose();
  }

  void _message(String message) {
    if (!mounted) return;

    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(content: Text(message)),
      );
  }

  Future<void> _sendOtp() async {
    final number = _phoneController.text.trim();

    if (!RegExp(r'^[6-9]\d{9}$').hasMatch(number)) {
      _message('Enter a valid 10-digit mobile number.');
      return;
    }

    if (_loading) return;

    setState(() => _loading = true);

    try {
      await _auth.verifyPhoneNumber(
        phoneNumber: '+91$number',
        timeout: const Duration(seconds: 60),

        verificationCompleted: (credential) async {
          await _signInWithCredential(credential);
        },

        verificationFailed: (error) {
          if (!mounted) return;
          setState(() => _loading = false);
          _message(
            error.message ?? 'Phone verification failed.',
          );
        },

        codeSent: (verificationId, resendToken) {
          if (!mounted) return;

          setState(() {
            _verificationId = verificationId;
            _otpSent = true;
            _loading = false;
          });

          _message('Verification code requested. Enter your OTP.');
        },

        codeAutoRetrievalTimeout: (verificationId) {
          if (!mounted) return;

          _verificationId = verificationId;
          setState(() => _loading = false);
        },
      );
    } on FirebaseAuthException catch (error) {
      if (!mounted) return;
      setState(() => _loading = false);
      _message(error.message ?? 'Unable to request OTP.');
    } catch (_) {
      if (!mounted) return;
      setState(() => _loading = false);
      _message('Something went wrong. Please try again.');
    }
  }

  Future<void> _verifyOtp() async {
    final otp = _otpController.text.trim();

    if (!RegExp(r'^\d{6}$').hasMatch(otp)) {
      _message('Enter a valid 6-digit OTP.');
      return;
    }

    final verificationId = _verificationId;

    if (verificationId == null) {
      _message('Request an OTP first.');
      return;
    }

    final credential = PhoneAuthProvider.credential(
      verificationId: verificationId,
      smsCode: otp,
    );

    await _signInWithCredential(credential);
  }


Future<void> _signInWithCredential(
  PhoneAuthCredential credential,
) async {
  if (!mounted || _verified || _loading) return;

  setState(() => _loading = true);

  try {
    final result = await _auth.signInWithCredential(credential);
    final firebaseUser = result.user;

    if (firebaseUser == null) {
      throw const AuthApiException(
        'Firebase authentication did not return a user.',
      );
    }

    final idToken = await firebaseUser.getIdToken();

    if (idToken == null || idToken.isEmpty) {
      throw const AuthApiException(
        'Unable to retrieve Firebase ID token.',
      );
    }

    // Django verifies the Firebase token and issues its own JWTs.
    final response = await AuthApi.firebaseLogin(
      idToken: idToken,
    );
    await SecureSessionStorage.saveSession(
      accessToken: response['access'] as String,
      refreshToken: response['refresh'] as String,
    );
    if (!mounted) return;

// Session has already been saved securely.
// Restart the app flow from the authentication gate.
Navigator.of(context).pushAndRemoveUntil(
  MaterialPageRoute(
    builder: (_) => const StartupGate(),
  ),
  (route) => false,
);

    // The Django JWTs are not yet persisted.
    // Secure session storage and home navigation come next.
  } on FirebaseAuthException catch (error) {
    if (!mounted) return;
    setState(() => _loading = false);
    _message(error.message ?? 'Firebase authentication failed.');
  } on AuthApiException catch (error) {
    if (!mounted) return;
    setState(() => _loading = false);
    _message(error.message);
  } catch (_) {
    if (!mounted) return;
    setState(() => _loading = false);
    _message('Unable to complete AIRway login. Please try again.');
  }
}

  @override
  Widget build(BuildContext context) {
    const green = Color(0xFF176B58);

    return Scaffold(
      appBar: AppBar(
        title: const Text('AIRway Sign In'),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 35),

              const Icon(
                Icons.phone_android_rounded,
                size: 60,
                color: green,
              ),

              const SizedBox(height: 24),

              Text(
                _verified
                    ? 'Phone Verified'
                    : _otpSent
                        ? 'Verify Your Number'
                        : 'Welcome to AIRway',
                style: const TextStyle(
                  fontSize: 28,
                  fontWeight: FontWeight.bold,
                ),
              ),

              const SizedBox(height: 12),

              Text(
                _verified
                    ? 'Firebase verification successful.'
                    : _otpSent
                        ? 'Enter the 6-digit verification code.'
                        : 'Enter your mobile number to continue.',
                style: const TextStyle(
                  fontSize: 16,
                  color: Colors.black54,
                ),
              ),

              const SizedBox(height: 32),

              if (!_otpSent && !_verified)
                TextField(
                  controller: _phoneController,
                  keyboardType: TextInputType.phone,
                  maxLength: 10,
                  inputFormatters: [
                    FilteringTextInputFormatter.digitsOnly,
                  ],
                  decoration: const InputDecoration(
                    labelText: 'Mobile Number',
                    prefixText: '+91 ',
                    border: OutlineInputBorder(),
                  ),
                ),

              if (_otpSent && !_verified)
                TextField(
                  controller: _otpController,
                  keyboardType: TextInputType.number,
                  maxLength: 6,
                  inputFormatters: [
                    FilteringTextInputFormatter.digitsOnly,
                  ],
                  decoration: const InputDecoration(
                    labelText: '6-digit OTP',
                    border: OutlineInputBorder(),
                  ),
                ),

              const SizedBox(height: 20),

              if (!_verified)
                SizedBox(
                  width: double.infinity,
                  height: 54,
                  child: FilledButton(
                    onPressed: _loading
                        ? null
                        : _otpSent
                            ? _verifyOtp
                            : _sendOtp,
                    child: _loading
                        ? const SizedBox(
                            width: 22,
                            height: 22,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                            ),
                          )
                        : Text(
                            _otpSent ? 'Verify OTP' : 'Send OTP',
                          ),
                  ),
                ),

              if (_otpSent && !_verified)
                TextButton(
                  onPressed: _loading
                      ? null
                      : () {
                          setState(() {
                            _otpSent = false;
                            _verificationId = null;
                            _otpController.clear();
                          });
                        },
                  child: const Text('Change Mobile Number'),
                ),

              if (_verified)
                const Center(
                  child: Icon(
                    Icons.verified_rounded,
                    color: green,
                    size: 76,
                  ),
                ),

              const SizedBox(height: 24),

              if (!_verified)
                const Center(
                  child: Text(
                    'By continuing, you consent to phone verification '
                    'through Firebase.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.black54,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
