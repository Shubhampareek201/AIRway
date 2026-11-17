
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:airway/features/auth/presentation/startup_gate.dart';
import 'package:flutter/services.dart';
import 'package:airway/core/network/auth_api.dart';
import 'package:airway/core/storage/secure_session_storage.dart';
import 'package:airway/features/account/presentation/legal_documents_screen.dart';
import 'package:airway/core/localization/airway_text.dart';
class PhoneLoginScreen extends StatefulWidget {
  const PhoneLoginScreen({super.key});

  @override
  State<PhoneLoginScreen> createState() => _PhoneLoginScreenState();
}

class _PhoneLoginScreenState extends State<PhoneLoginScreen> {
  final _phoneController = TextEditingController();
  final _otpController = TextEditingController();
  final _referralCodeController = TextEditingController();
  final _auth = FirebaseAuth.instance;

  bool _loading = false;
  bool _otpSent = false;
  bool _verified = false;
  bool _termsAccepted = false;
  bool _privacyAccepted = false;
  bool _credentialProcessing = false;
  String? _verificationId;

  @override
  void dispose() {
    _phoneController.dispose();
    _otpController.dispose();
    _referralCodeController.dispose();
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
  if (!mounted || _verified || _credentialProcessing) return;

  _credentialProcessing = true;
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
    _credentialProcessing = false;
    setState(() => _loading = false);
    _message(error.message ?? 'Firebase authentication failed.');
  } on AuthApiException catch (error) {
    if (!mounted) return;
    _credentialProcessing = false;
    setState(() => _loading = false);
    _message(error.message);
  } catch (_) {
    if (!mounted) return;
    _credentialProcessing = false;
    setState(() => _loading = false);
    _message('Unable to complete AIRway login. Please try again.');
  }
}

  Future<void> _retryBackendLogin() async {
    if (_loading || _credentialProcessing) return;
    if (!_termsAccepted || !_privacyAccepted) {
      _message('Please accept the Terms & Conditions and Privacy Policy.');
      return;
    }
    final firebaseUser = _auth.currentUser;
    if (firebaseUser == null) {
      _message('Please verify your phone number again.');
      return;
    }
    _credentialProcessing = true;
    setState(() => _loading = true);
    try {
      final idToken = await firebaseUser.getIdToken();
      if (idToken == null || idToken.isEmpty) {
        throw const AuthApiException('Unable to retrieve Firebase ID token.');
      }
      final response = await AuthApi.firebaseLogin(
        idToken: idToken,
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
      _credentialProcessing = false;
      setState(() => _loading = false);
      _message(error.message);
    } catch (_) {
      if (!mounted) return;
      _credentialProcessing = false;
      setState(() => _loading = false);
      _message('Unable to complete AIRway login. Please try again.');
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = AirwayText.tr;
    const green = Color(0xFF176B58);

    return Scaffold(
      appBar: AppBar(
        title: Text(t('AIRway Sign In', 'AIRway में लॉगिन करें')),
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
                    ? t('Phone Verified', 'फ़ोन सत्यापित')
                    : _otpSent
                        ? t('Verify Your Number', 'अपना नंबर सत्यापित करें')
                        : t('Welcome to AIRway', 'AIRway में आपका स्वागत है'),
                style: const TextStyle(
                  fontSize: 28,
                  fontWeight: FontWeight.bold,
                ),
              ),

              const SizedBox(height: 12),

              Text(
                _verified
                    ? t('Firebase verification successful.', 'Firebase सत्यापन सफल रहा।')
                    : _otpSent
                        ? t('Enter the 6-digit verification code.', '6 अंकों का सत्यापन कोड दर्ज करें।')
                        : t('Enter your mobile number to continue.', 'जारी रखने के लिए अपना मोबाइल नंबर दर्ज करें।'),
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
                  decoration: InputDecoration(
                    labelText: t('Mobile Number', 'मोबाइल नंबर'),
                    prefixText: '+91 ',
                    border: OutlineInputBorder(),
                  ),
                ),

              if (!_verified) ...[
                const SizedBox(height: 14),
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
                  title: Text(t('I have read and agree to the Privacy Policy', 'मैंने गोपनीयता नीति पढ़ ली है और सहमत हूँ')),
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
                const SizedBox(height: 14),
                TextField(
                  controller: _referralCodeController,
                  textCapitalization: TextCapitalization.characters,
                  inputFormatters: [FilteringTextInputFormatter.allow(RegExp('[A-Za-z0-9]'))],
                  decoration: InputDecoration(
                    labelText: t('Referral Code (Optional)', 'रेफ़रल कोड (वैकल्पिक)'),
                    helperText: t('Apply a friend’s code when creating a new account.', 'नया खाता बनाते समय दोस्त का कोड लागू करें।'),
                    border: OutlineInputBorder(),
                  ),
                ),
              ],

              if (_otpSent && !_verified)
                TextField(
                  controller: _otpController,
                  keyboardType: TextInputType.number,
                  maxLength: 6,
                  inputFormatters: [
                    FilteringTextInputFormatter.digitsOnly,
                  ],
                  decoration: InputDecoration(
                    labelText: t('6-digit OTP', '6 अंकों का OTP'),
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
                            _otpSent ? t('Verify OTP', 'OTP सत्यापित करें') : t('Send OTP', 'OTP भेजें'),
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
                  child: Text(t('Change Mobile Number', 'मोबाइल नंबर बदलें')),
                ),

              if (!_verified && _auth.currentUser != null && !_loading && !_credentialProcessing)
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton(
                    onPressed: _retryBackendLogin,
                    child: Text(t('Continue after accepting policies', 'नीतियाँ स्वीकार करके जारी रखें')),
                  ),
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
                Center(
                  child: Text(
                    '${t('By continuing, you consent to phone verification ', 'जारी रखकर आप फ़ोन सत्यापन की सहमति देते हैं ')}'
                    '${t('through Firebase.', 'Firebase के माध्यम से।')}',
                    textAlign: TextAlign.center,
                    style: const TextStyle(
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
