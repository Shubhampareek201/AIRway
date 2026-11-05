import 'package:flutter/material.dart';
import 'package:airway/core/network/auth_api.dart';
import 'package:airway/core/storage/secure_session_storage.dart';
import 'package:airway/features/location/data/location_api.dart';
import 'package:airway/features/location/presentation/location_selection_screen.dart';
import 'package:airway/features/customer/presentation/customer_home_screen.dart';
import 'package:airway/features/welcome/presentation/welcome_screen.dart';
import 'package:airway/features/auth/presentation/profile_completion_screen.dart';
import 'package:airway/features/worker/presentation/worker_application_screen.dart';
import 'package:airway/features/worker/presentation/worker_dashboard_screen.dart';

/// Determines whether the customer needs authentication, profile completion,
/// an address, or can continue into the app. It never treats network errors as logout.
class StartupGate extends StatefulWidget {
  const StartupGate({super.key});

  @override
  State<StartupGate> createState() => _StartupGateState();
}

/// Represents the startup decision with worker profile data if applicable
class _StartupRoute {
  final int route;
  final Map<String, dynamic>? workerProfile;

  _StartupRoute(this.route, {this.workerProfile});
}

class _StartupGateState extends State<StartupGate> {
  late Future<_StartupRoute> _startup;

  static const int routeWelcome = 0;
  static const int routeLocation = 1;
  static const int routeCustomerHome = 2;
  static const int routeProfileComplete = 3;
  static const int routeWorkerDashboard = 4;
  static const int routeWorkerPending = 5;
  static const int routeWorkerRejected = 6;

  @override
  void initState() {
    super.initState();
    _startup = _decide();
  }

  Future<_StartupRoute> _decide() async {
    final session = await SecureSessionStorage.readSession();
    if (session == null) return _StartupRoute(routeWelcome);

    if (!await AuthApi.validateSession(accessToken: session.accessToken)) {
      final refreshed = await AuthApi.refreshSession(
        refreshToken: session.refreshToken,
      );
      if (refreshed == null) {
        await SecureSessionStorage.clearSession();
        return _StartupRoute(routeWelcome);
      }
      await SecureSessionStorage.saveSession(
        accessToken: refreshed['access'] as String,
        refreshToken: refreshed['refresh'] as String? ?? session.refreshToken,
      );
    }

    // Check if profile is complete via /me/ endpoint
    Map<String, dynamic>? meResponse;
    try {
      meResponse = await LocationApi.request('/api/v1/auth/me/') as Map<String, dynamic>?;
    } catch (_) {
      // If /me/ fails, continue to address check
    }

    if (meResponse != null) {
      final workerProfile = meResponse['worker_profile'];
      if (workerProfile != null) {
        final Map<String, dynamic> wp = Map<String, dynamic>.from(workerProfile);
        final status = wp['status'] as String?;
        if (status == 'approved') {
          return _StartupRoute(routeWorkerDashboard, workerProfile: wp);
        }
        if (status == 'pending') {
          return _StartupRoute(routeWorkerPending, workerProfile: wp);
        }
        if (status == 'rejected') {
          return _StartupRoute(routeWorkerRejected, workerProfile: wp);
        }
      }

      if (meResponse['profile_complete'] == false) {
        return _StartupRoute(routeProfileComplete); // Profile completion needed
      }
    }

    final response = await LocationApi.request('/api/v1/auth/addresses/');
    final list = response is List
        ? response
        : response is Map ? response['results'] : null;
    if (list is! List) throw const FormatException('Invalid address list.');
    // Empty -> location setup; saved address -> customer home.
    return _StartupRoute(list.isEmpty ? routeLocation : routeCustomerHome);
  }

  Widget _buildWorkerPendingScreen(Map<String, dynamic> workerProfile) {
    // Pending applications don't show rejection reason (that's for rejected ones)
    return Scaffold(
      appBar: AppBar(title: const Text('Worker Application Status')),
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.pending_actions, size: 64, color: Colors.orange),
                const SizedBox(height: 20),
                const Text(
                  'Your Worker Application',
                  style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 12),
                const Text(
                  'Your application is pending admin verification.\n\nYou will receive a notification once your application is approved.\n\nIn the meantime, you can continue using AIRway as a customer.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.grey),
                ),
                const SizedBox(height: 24),
                ElevatedButton.icon(
                  onPressed: () {
                    Navigator.of(context).push(
                      MaterialPageRoute(builder: (_) => const WorkerApplicationScreen()),
                    );
                  },
                  icon: const Icon(Icons.edit),
                  label: const Text('Continue Application'),
                ),
                const SizedBox(height: 12),
                TextButton(
                  onPressed: () {
                    Navigator.of(context).pushAndRemoveUntil(
                      MaterialPageRoute(builder: (_) => const CustomerHomeScreen()),
                      (route) => false,
                    );
                  },
                  child: const Text('Switch to Customer Mode'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildWorkerRejectedScreen(Map<String, dynamic> workerProfile) {
    final rejectionReason = workerProfile['rejection_reason'] as String?;
    return Scaffold(
      appBar: AppBar(title: const Text('Application Not Approved')),
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.cancel, size: 64, color: Colors.red),
                const SizedBox(height: 20),
                const Text(
                  'Application Rejected',
                  style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 12),
                if (rejectionReason != null && rejectionReason.isNotEmpty) ...[
                  Text(
                    'Reason: $rejectionReason',
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: Colors.grey),
                  ),
                  const SizedBox(height: 16),
                ] else ...[
                  const Text(
                    'Your worker application was not approved.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.grey),
                  ),
                  const SizedBox(height: 16),
                ],
                const Text(
                  'You can reapply once you\'ve addressed the concerns.\n\nOr continue using AIRway as a customer.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.grey),
                ),
                const SizedBox(height: 24),
                ElevatedButton.icon(
                  onPressed: () {
                    Navigator.of(context).push(
                      MaterialPageRoute(builder: (_) => const WorkerApplicationScreen()),
                    );
                  },
                  icon: const Icon(Icons.refresh),
                  label: const Text('Reapply'),
                ),
                const SizedBox(height: 12),
                TextButton(
                  onPressed: () {
                    Navigator.of(context).pushAndRemoveUntil(
                      MaterialPageRoute(builder: (_) => const CustomerHomeScreen()),
                      (route) => false,
                    );
                  },
                  child: const Text('Switch to Customer Mode'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<_StartupRoute>(
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

        final route = snapshot.data!;
        switch (route.route) {
          case routeWelcome:
            return const WelcomeScreen();
          case routeLocation:
            return const LocationSelectionScreen();
          case routeCustomerHome:
            return const CustomerHomeScreen();
          case routeProfileComplete:
            return const ProfileCompletionScreen();
          case routeWorkerDashboard:
            return const WorkerDashboardScreen();
          case routeWorkerPending:
            return _buildWorkerPendingScreen(route.workerProfile!);
          case routeWorkerRejected:
            return _buildWorkerRejectedScreen(route.workerProfile!);
          default:
            return const Scaffold(body: Center(child: Text('Unable to start AIRway.')));
        }
      },
    );
  }
}