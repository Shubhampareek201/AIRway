import 'package:flutter/material.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:airway/core/network/auth_api.dart';
import 'package:airway/core/storage/secure_session_storage.dart';
import 'package:airway/features/auth/presentation/startup_gate.dart';

class ProfileCompletionScreen extends StatefulWidget {
  const ProfileCompletionScreen({super.key});

  @override
  State<ProfileCompletionScreen> createState() => _ProfileCompletionScreenState();
}

class _ProfileCompletionScreenState extends State<ProfileCompletionScreen> {
  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  String? _selectedGender;
  bool _loading = false;
  bool _googleLoading = false;

  static const List<String> _genders = ['male', 'female', 'other', 'prefer_not_to_say'];

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    super.dispose();
  }

  void _message(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _completeProfile() async {
    final name = _nameController.text.trim();
    final email = _emailController.text.trim();
    final gender = _selectedGender;

    if (name.isEmpty) {
      _message('Please enter your full name.');
      return;
    }
    if (email.isNotEmpty && !RegExp(r'^[\w-\.]+@([\w-]+\.)+[\w-]{2,4}$').hasMatch(email)) {
      _message('Enter a valid email address.');
      return;
    }
    if (_loading) return;

    setState(() => _loading = true);

    try {
      final session = await SecureSessionStorage.readSession();
      if (session == null) {
        _message('Session expired. Please login again.');
        if (!mounted) return;
        Navigator.of(context).pushAndRemoveUntil(
          MaterialPageRoute(builder: (_) => const StartupGate()),
          (route) => false,
        );
        return;
      }

      final response = await AuthApi.completeProfile(
        accessToken: session.accessToken,
        name: name,
        email: email.isEmpty ? null : email,
        gender: gender,
      );

      if (!mounted) return;
      if (response['profile_complete'] == true) {
        Navigator.of(context).pushAndRemoveUntil(
          MaterialPageRoute(builder: (_) => const StartupGate()),
          (route) => false,
        );
      } else {
        _message('Profile completion failed. Please try again.');
      }
    } on AuthApiException catch (error) {
      if (!mounted) return;
      _message(error.message);
    } catch (_) {
      if (!mounted) return;
      _message('Unable to complete profile. Please try again.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _fillFromGoogle() async {
    if (_googleLoading) return;
    setState(() => _googleLoading = true);

    try {
      final GoogleSignIn googleSignIn = GoogleSignIn(
        scopes: ['email', 'profile'],
      );

      final GoogleSignInAccount? account = await googleSignIn.signIn();

      if (account == null) {
        _message('Google Sign-In cancelled.');
        return;
      }

      if (!mounted) return;

      // Fill the form with Google account info
      _nameController.text = account.displayName ?? '';
      _emailController.text = account.email;

      // For gender, we can't get it from Google directly, so leave as is
      _message('Name and email filled from Google account.');
    } on Exception catch (e) {
      if (!mounted) return;
      _message('Google Sign-In failed: ${e.toString()}');
    } finally {
      if (mounted) setState(() => _googleLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    const green = Color(0xFF176B58);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Complete Your Profile'),
        automaticallyImplyLeading: false,
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 10),
              const Text(
                'Welcome to AIRway!',
                style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              const Text(
                'Please complete your profile to continue.',
                style: TextStyle(fontSize: 16, color: Colors.black54),
              ),
              const SizedBox(height: 32),
              TextField(
                controller: _nameController,
                decoration: const InputDecoration(
                  labelText: 'Full Name *',
                  border: OutlineInputBorder(),
                ),
                textCapitalization: TextCapitalization.words,
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _emailController,
                keyboardType: TextInputType.emailAddress,
                decoration: const InputDecoration(
                  labelText: 'Email Address',
                  border: OutlineInputBorder(),
                  helperText: 'Optional, but recommended for account recovery',
                ),
              ),
              const SizedBox(height: 16),
              DropdownButtonFormField<String>(
                initialValue: _selectedGender,
                decoration: const InputDecoration(
                  labelText: 'Gender',
                  border: OutlineInputBorder(),
                ),
                items: _genders
                    .map((g) => DropdownMenuItem(
                          value: g,
                          child: Text(g
                              .split('_')
                              .map((w) => w[0].toUpperCase() + w.substring(1))
                              .join(' ')),
                        ))
                    .toList(),
                onChanged: (v) => setState(() => _selectedGender = v),
              ),
              const SizedBox(height: 24),
              SizedBox(
                width: double.infinity,
                height: 54,
                child: FilledButton(
                  style: FilledButton.styleFrom(backgroundColor: green),
                  onPressed: _loading ? null : _completeProfile,
                  child: _loading
                      ? const SizedBox(
                          width: 22,
                          height: 22,
                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                        )
                      : const Text('Continue'),
                ),
              ),
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                height: 54,
                child: OutlinedButton.icon(
                  icon: _googleLoading
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : Image.asset(
                          'assets/images/google_logo.png',
                          height: 24,
                          errorBuilder: (_, __, ____) => const Icon(Icons.g_mobiledata, size: 24),
                        ),
                  label: const Text('Fill from Google Account'),
                  onPressed: _googleLoading ? null : _fillFromGoogle,
                ),
              ),
              const SizedBox(height: 16),
              Center(
                child: Text(
                  'You can update this information later in Settings.',
                  style: TextStyle(fontSize: 12, color: Colors.grey[600]),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}