
import 'package:flutter/material.dart';
import 'package:airway/features/auth/presentation/login_screen.dart';
class WelcomeScreen extends StatelessWidget {
  const WelcomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    const green = Color(0xFF176B58);

    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 28),
          child: Column(
            children: [
              const Spacer(flex: 2),

              Container(
                width: 112,
                height: 112,
                decoration: BoxDecoration(
                  color: green,
                  borderRadius: BorderRadius.circular(32),
                  boxShadow: [
                    BoxShadow(
                      color: green.withValues(alpha: 0.18),
                      blurRadius: 30,
                      offset: const Offset(0, 12),
                    ),
                  ],
                ),
                child: const Icon(
                  Icons.home_repair_service_rounded,
                  color: Colors.white,
                  size: 58,
                ),
              ),

              const SizedBox(height: 30),

              const Text(
                'AIRway',
                style: TextStyle(
                  fontSize: 44,
                  fontWeight: FontWeight.w800,
                  letterSpacing: -1.5,
                  color: green,
                ),
              ),

              const SizedBox(height: 10),

              const Text(
                'Home services, made simple.',
                style: TextStyle(
                  fontSize: 17,
                  color: Colors.black54,
                ),
              ),

              const SizedBox(height: 24),

              const Text(
                'Trusted professionals at your doorstep.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 16,
                  height: 1.5,
                ),
              ),

              const Spacer(flex: 2),

              SizedBox(
                width: double.infinity,
                height: 56,
                child: FilledButton(
                  onPressed: () {
  Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => const LoginScreen(),
    ),
  );
},
                  style: FilledButton.styleFrom(
                    backgroundColor: green,
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16),
                    ),
                  ),
                  child: const Text(
                    'Get Started',
                    style: TextStyle(
                      fontSize: 17,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ),

              const SizedBox(height: 16),

              const Text(
                'Starting in Rawatbhata',
                style: TextStyle(
                  color: Colors.black54,
                  fontSize: 13,
                ),
              ),

              const SizedBox(height: 28),
            ],
          ),
        ),
      ),
    );
  }
}
