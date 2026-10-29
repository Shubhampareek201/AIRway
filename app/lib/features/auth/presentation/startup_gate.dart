import 'package:flutter/material.dart';
import 'package:airway/core/network/auth_api.dart';
import 'package:airway/core/storage/secure_session_storage.dart';
import 'package:airway/features/location/data/location_api.dart';
import 'package:airway/features/location/presentation/location_selection_screen.dart';
import 'package:airway/features/customer/presentation/customer_home_screen.dart';
import 'package:airway/features/welcome/presentation/welcome_screen.dart';

/// Determines whether the customer needs authentication, an address,
/// or can continue into the app. It never treats network errors as logout.
class StartupGate extends StatefulWidget {
  const StartupGate({super.key});

  @override
  State<StartupGate> createState() => _StartupGateState();
}

class _StartupGateState extends State<StartupGate> {
  late Future<int> _startup;

  @override
  void initState() {
    super.initState();
    _startup = _decide();
  }

  Future<int> _decide() async {
    final session = await SecureSessionStorage.readSession();
    if (session == null) return 0;
    if (!await AuthApi.validateSession(accessToken: session.accessToken)) {
      final refreshed = await AuthApi.refreshSession(
        refreshToken: session.refreshToken,
      );
      if (refreshed == null) {
        await SecureSessionStorage.clearSession();
        return 0;
      }
      await SecureSessionStorage.saveSession(
        accessToken: refreshed['access'] as String,
        refreshToken: refreshed['refresh'] as String? ?? session.refreshToken,
      );
    }

    final response = await LocationApi.request('/api/v1/auth/addresses/');
    final list = response is List
        ? response
        : response is Map ? response['results'] : null;
    if (list is! List) throw const FormatException('Invalid address list.');
    // Empty -> location setup; saved address -> customer home.
    return list.isEmpty ? 1 : 2;
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<int>(
      future: _startup,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          );
        }
        if (snapshot.hasError) {
          return Scaffold(
            body: SafeArea(
              child: Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.wifi_off_outlined, size: 40),
                      const SizedBox(height: 14),
                      const Text('Unable to connect to AIRway.'),
                      const SizedBox(height: 12),
                      FilledButton(
                        onPressed: () {
                          setState(() {
                            _startup = _decide();
                          });
                        },
                        child: const Text('Retry'),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          );
        }
        switch (snapshot.data) {
          case 0:
            return const WelcomeScreen();
          case 1:
            return const LocationSelectionScreen();
          case 2:
            return const CustomerHomeScreen();
          default:
            return const Scaffold(body: Center(child: Text('Unable to start AIRway.')));
        }
      },
    );
  }
}
