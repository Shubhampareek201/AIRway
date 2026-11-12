import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/core/storage/secure_session_storage.dart';
import 'package:airway/features/welcome/presentation/welcome_screen.dart';
import 'package:airway/features/customer/presentation/customer_home_screen.dart';
import 'package:airway/features/worker/data/worker_app_api.dart';
import 'package:airway/features/worker/data/worker_api.dart';
import 'package:airway/features/worker/data/worker_models.dart';
import 'package:airway/features/worker/presentation/assigned_job_screen.dart';
import 'package:airway/features/worker/presentation/job_offers_screen.dart';

class WorkerDashboardScreen extends StatefulWidget {
  const WorkerDashboardScreen({super.key});

  @override
  State<WorkerDashboardScreen> createState() => _WorkerDashboardScreenState();
}

class _WorkerDashboardScreenState extends State<WorkerDashboardScreen> {
  WorkerProfile? _profile;
  List<Map<String, dynamic>> _assignedJobs = [];
  List<WorkerOffer> _offers = [];
  List<Map<String, dynamic>> _earnings = [];
  bool _loading = true;
  bool _availabilitySaving = false;
  String? _error;
  String? _offersError;
  String? _jobsError;
  String? _earningsError;
  int _selectedTab = 0;

  static const _tabTitles = ['Home', 'Jobs', 'Earnings', 'Profile'];

  @override
  void initState() {
    super.initState();
    _loadDashboard();
  }

  Future<T?> _loadSection<T>(
    Future<T> Function() load,
    void Function(String message) onError,
  ) async {
    try {
      return await load();
    } catch (error) {
      onError(error.toString().replaceFirst('Exception: ', ''));
      return null;
    }
  }

  Future<void> _loadDashboard({bool showLoader = true}) async {
    if (mounted) {
      setState(() {
        if (showLoader) _loading = true;
        _error = null;
        _offersError = null;
        _jobsError = null;
        _earningsError = null;
      });
    }

    String? profileError;
    String? offersError;
    String? jobsError;
    String? earningsError;

    final profileFuture = _loadSection(
      WorkerApi.getMyProfile,
      (message) => profileError = message,
    );
    final offersFuture = _loadSection(
      WorkerApi.getJobOffers,
      (message) => offersError = message,
    );
    final jobsFuture = _loadSection(
      WorkerApi.getAssignedJobs,
      (message) => jobsError = message,
    );
    final earningsFuture = _loadSection(
      WorkerApi.getEarnings,
      (message) => earningsError = message,
    );

    try {
      final profile = await profileFuture;
      if (profile == null) {
        throw Exception(profileError ?? 'Could not load your worker profile.');
      }
      if (profile.status != 'approved') {
        throw Exception('Your worker profile is ${profile.status}. Contact AIRway support.');
      }

      final results = await Future.wait<dynamic>([
        offersFuture,
        jobsFuture,
        earningsFuture,
      ]);
      if (!mounted) return;

      setState(() {
        _profile = profile;
        if (results[0] != null) _offers = results[0] as List<WorkerOffer>;
        if (results[1] != null) {
          _assignedJobs = results[1] as List<Map<String, dynamic>>;
        }
        if (results[2] != null) {
          _earnings = results[2] as List<Map<String, dynamic>>;
        }
        _offersError = offersError;
        _jobsError = jobsError;
        _earningsError = earningsError;
      });
    } catch (error) {
      if (mounted) {
        setState(() {
          _error = error.toString().replaceFirst('Exception: ', '');
        });
      }
    } finally {
      if (mounted && showLoader) setState(() => _loading = false);
    }
  }

  Future<void> _refresh() => _loadDashboard(showLoader: false);

  Future<void> _toggleAvailability(bool value) async {
    if (_availabilitySaving) return;
    setState(() => _availabilitySaving = true);
    try {
      final actual = await WorkerApi.updateOnlineStatus(value);
      if (mounted && _profile != null) {
        setState(() {
          _profile = WorkerProfile(
            id: _profile!.id,
            status: _profile!.status,
            name: _profile!.name,
            phone: _profile!.phone,
            upiId: _profile!.upiId,
            isOnline: actual,
            ratingAvg: _profile!.ratingAvg,
            experienceYears: _profile!.experienceYears,
            rejectionReason: _profile!.rejectionReason,
            qualification: _profile!.qualification,
            equipmentDetails: _profile!.equipmentDetails,
            residentialAddress: _profile!.residentialAddress,
            landmark: _profile!.landmark,
            bio: _profile!.bio,
            services: _profile!.services,
            zones: _profile!.zones,
            schedules: _profile!.schedules,
            documents: _profile!.documents,
          );
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(actual ? 'You are now online' : 'You are now offline')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not update availability: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _availabilitySaving = false);
    }
  }

  Future<void> _switchToCustomerMode() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Switch to Customer?'),
        content: const Text('You will return to Customer Home using this same account. Your worker profile and job history will remain saved.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(dialogContext, true), child: const Text('Switch')),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      await WorkerAppApi.switchToCustomerMode();
      if (!mounted) return;
      Navigator.of(context).pushAndRemoveUntil(MaterialPageRoute(builder: (_) => const CustomerHomeScreen()), (_) => false);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not switch to Customer mode: $e')));
    }
  }

  Future<void> _endSession({required bool switchAccount}) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(switchAccount ? 'Switch account?' : 'Log out?'),
        content: Text(switchAccount ? 'You will be signed out so another AIRway account can sign in on this device.' : 'You will be securely signed out of AIRway.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(dialogContext, true), child: Text(switchAccount ? 'Continue' : 'Log out')),
        ],
      ),
    );
    if (confirmed != true) return;
    await SecureSessionStorage.clearSession();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(MaterialPageRoute(builder: (_) => const WelcomeScreen()), (_) => false);
  }
  void _openOffers() {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const JobOffersScreen()),
    ).then((_) => _refresh());
  }

  void _openAssignedJobs({int? assignmentId}) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => AssignedJobScreen(assignmentId: assignmentId),
      ),
    ).then((_) => _refresh());
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    if (_error != null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Worker Dashboard')),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.cloud_off_rounded, size: 48, color: AirwayColors.error),
                const SizedBox(height: 14),
                Text(_error!, textAlign: TextAlign.center),
                const SizedBox(height: 18),
                FilledButton.icon(
                  onPressed: () => _loadDashboard(),
                  icon: const Icon(Icons.refresh),
                  label: const Text('Try again'),
                ),
              ],
            ),
          ),
        ),
      );
    }

    final profile = _profile!;
    return Scaffold(
      appBar: AppBar(
        title: Text(_tabTitles[_selectedTab]),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            onPressed: _refresh,
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _refresh,
        // Keep exactly one scrollable tab mounted at a time. Keeping several
        // ListViews alive inside an IndexedStack can trigger competing sliver
        // layout passes on some Android devices.
        child: _buildSelectedTab(profile),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedTab,
        onDestinationSelected: (index) => setState(() => _selectedTab = index),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home_rounded), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.work_outline_rounded), selectedIcon: Icon(Icons.work_rounded), label: 'Jobs'),
          NavigationDestination(icon: Icon(Icons.account_balance_wallet_outlined), selectedIcon: Icon(Icons.account_balance_wallet_rounded), label: 'Earnings'),
          NavigationDestination(icon: Icon(Icons.person_outline_rounded), selectedIcon: Icon(Icons.person_rounded), label: 'Profile'),
        ],
      ),
    );
  }

  Widget _buildSelectedTab(WorkerProfile profile) {
    return switch (_selectedTab) {
      0 => _buildHomeTab(profile),
      1 => _buildJobsTab(),
      2 => _buildEarningsTab(),
      _ => _buildProfileTab(profile),
    };
  }

  Widget _page(List<Widget> children) => ListView(
        key: PageStorageKey<String>(_tabTitles[_selectedTab]),
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
        children: children,
      );

  Widget _buildHomeTab(WorkerProfile profile) {
    final pendingCount = _offers.where((o) => o.status == WorkerOffer.pending).length;
    final activeJobs = _assignedJobs.where((j) {
      final status = j['status']?.toString();
      return status != 'completed' && status != 'cancelled';
    }).length;

    return _page([
      _buildWelcomeCard(profile),
      const SizedBox(height: 16),
      _buildAvailabilityCard(profile),
      const SizedBox(height: 16),
      Row(
        children: [
          Expanded(child: _buildMetricCard('New offers', '$pendingCount', Icons.notifications_active_outlined)),
          const SizedBox(width: 12),
          Expanded(child: _buildMetricCard('Active jobs', '$activeJobs', Icons.assignment_outlined)),
        ],
      ),
      const SizedBox(height: 20),
      _sectionHeading('Your next steps', action: 'View jobs', onAction: () => setState(() => _selectedTab = 1)),
      const SizedBox(height: 8),
      _buildNextJobCard(),
      const SizedBox(height: 16),
      _sectionHeading('Recent job offers', action: 'View all', onAction: _openOffers),
      const SizedBox(height: 8),
      if (_offersError != null)
        _SectionErrorCard(message: _offersError!, onRetry: _refresh)
      else ...[
        ..._offers.where((o) => o.status == WorkerOffer.pending).take(3).map(_buildOfferPreview),
        if (pendingCount == 0)
          const _EmptyCard(icon: Icons.inbox_outlined, title: 'No new offers', subtitle: 'New job offers will appear here.'),
      ],
    ]);
  }

  Widget _buildJobsTab() {
    final active = _assignedJobs.where((j) => j['status']?.toString() != 'completed' && j['status']?.toString() != 'cancelled').toList();
    final completed = _assignedJobs.where((j) => j['status']?.toString() == 'completed').toList();
    final pendingOffers = _offers.where((o) => o.status == WorkerOffer.pending).toList();

    return _page([
      _sectionHeading('New job offers', action: 'View all', onAction: _openOffers),
      const SizedBox(height: 8),
      if (_offersError != null)
        _SectionErrorCard(message: _offersError!, onRetry: _refresh)
      else if (pendingOffers.isEmpty)
        const _EmptyCard(icon: Icons.inbox_outlined, title: 'No new offers', subtitle: 'Check back when customers request a service.')
      else
        ...pendingOffers.take(4).map(_buildOfferPreview),
      const SizedBox(height: 20),
      _sectionHeading('Assigned jobs', action: 'Open jobs', onAction: _openAssignedJobs),
      const SizedBox(height: 8),
      if (_jobsError != null)
        _SectionErrorCard(message: _jobsError!, onRetry: _refresh)
      else if (active.isEmpty)
        const _EmptyCard(icon: Icons.work_outline, title: 'No active jobs', subtitle: 'Accepted jobs will appear here.')
      else
        ...active.take(5).map(_buildJobPreview),
      if (completed.isNotEmpty) ...[
        const SizedBox(height: 20),
        Text('Completed jobs: ${completed.length}', style: const TextStyle(fontWeight: FontWeight.w600)),
      ],
    ]);
  }

  Widget _buildEarningsTab() {
    final total = _earnings.fold<double>(
      0,
      (sum, item) => sum + (double.tryParse('${item['amount']}') ?? 0),
    );
    return _page([
      Card(
        color: AirwayColors.primary,
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Recorded earnings', style: TextStyle(color: Colors.white70)),
              const SizedBox(height: 8),
              Text(
                NumberFormat.currency(locale: 'en_IN', symbol: '₹', decimalDigits: 0).format(total),
                style: const TextStyle(color: Colors.white, fontSize: 30, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 4),
              Text('${_earnings.length} earning records', style: const TextStyle(color: Colors.white70)),
            ],
          ),
        ),
      ),
      const SizedBox(height: 20),
      const Text('Recent activity', style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold)),
      const SizedBox(height: 8),
      if (_earningsError != null)
        _SectionErrorCard(message: _earningsError!, onRetry: _refresh)
      else if (_earnings.isEmpty)
        const _EmptyCard(icon: Icons.account_balance_wallet_outlined, title: 'No earnings yet', subtitle: 'Completed and credited jobs will show here.')
      else
        ..._earnings.map(_buildEarningRow),
      const SizedBox(height: 8),
      Text(
        'Earnings shown are records returned by AIRway. Final payout and settlement may be handled separately.',
        style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12),
      ),
    ]);
  }

  Widget _buildProfileTab(WorkerProfile profile) {
    return _page([
      Card(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            children: [
              CircleAvatar(
                radius: 38,
                backgroundColor: AirwayColors.primary.withValues(alpha: 0.12),
                child: Icon(Icons.person_rounded, size: 42, color: AirwayColors.primary),
              ),
              const SizedBox(height: 12),
              Text(profile.name?.trim().isNotEmpty == true ? profile.name! : 'AIRway Worker',
                  style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
              Text(profile.phone ?? 'Phone not available', style: TextStyle(color: AirwayColors.textSecondary)),
              const SizedBox(height: 12),
              Chip(
                avatar: const Icon(Icons.verified_rounded, size: 18, color: Colors.green),
                label: const Text('Verified worker'),
                backgroundColor: Colors.green.shade50,
              ),
            ],
          ),
        ),
      ),
      const SizedBox(height: 16),
      _sectionHeading('Your details'),
      const SizedBox(height: 8),
      _detailTile(Icons.star_outline_rounded, 'Rating', profile.ratingAvg == null ? 'Not rated yet' : profile.ratingAvg!.toStringAsFixed(1)),
      _detailTile(Icons.work_history_outlined, 'Experience', '${profile.experienceYears ?? 0} years'),
      _detailTile(Icons.school_outlined, 'Qualification', profile.qualification?.isNotEmpty == true ? profile.qualification! : 'Not added'),
      _detailTile(Icons.home_outlined, 'Residential address', profile.residentialAddress?.isNotEmpty == true ? profile.residentialAddress! : 'Not added'),
      _detailTile(Icons.location_on_outlined, 'Landmark', profile.landmark?.isNotEmpty == true ? profile.landmark! : 'Not added'),
      _detailTile(Icons.handyman_outlined, 'Tools / equipment', profile.equipmentDetails?.isNotEmpty == true ? profile.equipmentDetails! : 'Not added'),
      _detailTile(Icons.payments_outlined, 'UPI ID', (profile.upiId?.isNotEmpty == true) ? profile.upiId! : 'Not added'),
      _detailTile(Icons.verified_user_outlined, 'Application', 'Approved'),
      if (profile.bio?.isNotEmpty == true) _detailTile(Icons.person_outline_rounded, 'About your work', profile.bio!),
      if (profile.documents.isNotEmpty) _detailTile(
        Icons.description_outlined,
        'Verification documents',
        profile.documents.map((item) {
          final type = item['doc_type']?.toString() ?? 'Document';
          final status = item['status']?.toString() ?? 'pending';
          return '$type: $status';
        }).join(', '),
      ),
      if (profile.services.isNotEmpty) _detailTile(Icons.category_outlined, 'Services', profile.services.join(', ')),
      if (profile.zones.isNotEmpty) _detailTile(Icons.map_outlined, 'Service areas', profile.zones.join(', ')),
      if (profile.schedules.isNotEmpty) _detailTile(
        Icons.schedule_outlined,
        'Working hours',
        profile.schedules.map((item) {
          final day = item['weekday_display']?.toString() ?? '';
          final start = item['start_time']?.toString() ?? '';
          final end = item['end_time']?.toString() ?? '';
          final range = start.length >= 5 && end.length >= 5
              ? '${start.substring(0, 5)}–${end.substring(0, 5)}'
              : '';
          return [day, range].where((value) => value.isNotEmpty).join(' ');
        }).join(', '),
      ),
      const SizedBox(height: 16),
      OutlinedButton.icon(onPressed: _refresh, icon: const Icon(Icons.sync), label: const Text('Refresh profile')),
      const SizedBox(height: 20),
      _sectionHeading('Account'),
      Card(
        child: Column(children: [
          ListTile(leading: const Icon(Icons.storefront_outlined), title: const Text('Switch to Customer'), subtitle: const Text('Return to Customer Home with this account'), trailing: const Icon(Icons.chevron_right_rounded), onTap: _switchToCustomerMode),
          const Divider(height: 1),
          ListTile(leading: const Icon(Icons.switch_account_outlined), title: const Text('Switch Account'), subtitle: const Text('Sign out and use another account'), trailing: const Icon(Icons.chevron_right_rounded), onTap: () => _endSession(switchAccount: true)),
          const Divider(height: 1),
          ListTile(leading: Icon(Icons.logout_rounded, color: AirwayColors.error), title: Text('Log out', style: TextStyle(color: AirwayColors.error)), subtitle: const Text('Securely sign out of AIRway'), onTap: () => _endSession(switchAccount: false)),
        ]),
      ),
    ]);
  }

  Widget _buildWelcomeCard(WorkerProfile profile) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Hello, ${profile.name?.trim().isNotEmpty == true ? profile.name : 'Partner'}!',
                      style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 5),
                  Text('Ready for your next service?', style: TextStyle(color: AirwayColors.textSecondary)),
                ],
              ),
            ),
            CircleAvatar(
              radius: 25,
              backgroundColor: AirwayColors.primary.withValues(alpha: 0.12),
              child: Icon(Icons.handyman_outlined, color: AirwayColors.primary, size: 28),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAvailabilityCard(WorkerProfile profile) {
    return Card(
      child: SwitchListTile(
        value: profile.isOnline,
        onChanged: _availabilitySaving ? null : _toggleAvailability,
        secondary: Icon(
          profile.isOnline ? Icons.wifi_rounded : Icons.wifi_off_rounded,
          color: profile.isOnline ? Colors.green : AirwayColors.textSecondary,
        ),
        title: Text(profile.isOnline ? 'You are online' : 'You are offline',
            style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: Text(profile.isOnline ? 'You can receive new job offers' : 'Turn on to receive nearby job offers'),
      ),
    );
  }

  Widget _buildMetricCard(String label, String value, IconData icon) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: AirwayColors.primary),
            const SizedBox(height: 12),
            Text(value, style: const TextStyle(fontSize: 25, fontWeight: FontWeight.bold)),
            Text(label, style: TextStyle(color: AirwayColors.textSecondary)),
          ],
        ),
      ),
    );
  }

  Widget _buildNextJobCard() {
    if (_assignedJobs.isEmpty) {
      return const _EmptyCard(icon: Icons.event_available_outlined, title: 'Nothing scheduled yet', subtitle: 'Your assigned jobs will appear here.');
    }
    final job = _assignedJobs.first;
    return Card(
      child: ListTile(
        leading: Icon(Icons.assignment_outlined, color: AirwayColors.primary),
        title: Text(job['service_title']?.toString() ?? 'Assigned service'),
        subtitle: Text('Booking #${job['booking_id'] ?? job['id']} • ${_dateLabel(job['scheduled_at'])}'),
        trailing: const Icon(Icons.chevron_right_rounded),
        onTap: () => _openAssignedJobs(assignmentId: job['id'] as int?),
      ),
    );
  }

  Widget _buildJobPreview(Map<String, dynamic> job) {
    return Card(
      child: ListTile(
        leading: Icon(Icons.work_outline, color: AirwayColors.primary),
        title: Text(job['service_title']?.toString() ?? 'Service job'),
        subtitle: Text('Booking #${job['booking_id'] ?? job['id']} • ${_dateLabel(job['scheduled_at'])}'),
        trailing: const Icon(Icons.chevron_right_rounded),
        onTap: () => _openAssignedJobs(assignmentId: job['id'] as int?),
      ),
    );
  }

  Widget _buildOfferPreview(WorkerOffer offer) {
    return Card(
      child: ListTile(
        leading: Icon(Icons.notifications_active_outlined, color: AirwayColors.primary),
        title: Text('Booking #${offer.bookingId}'),
        subtitle: Text('Received ${_dateLabel(offer.offeredAt.toIso8601String())}'),
        trailing: const Icon(Icons.chevron_right_rounded),
        onTap: _openOffers,
      ),
    );
  }

  Widget _buildEarningRow(Map<String, dynamic> item) {
    final amount = double.tryParse('${item['amount']}') ?? 0;
    final title = item['service_title']?.toString().trim();
    return Card(
      child: ListTile(
        leading: const CircleAvatar(child: Icon(Icons.currency_rupee_rounded)),
        title: Text(title?.isNotEmpty == true ? title! : 'Service payment'),
        subtitle: Text('Booking #${item['booking_id'] ?? '—'} • ${_dateLabel(item['created_at'])}'),
        trailing: Text(
          '+${NumberFormat.currency(locale: 'en_IN', symbol: '₹', decimalDigits: 0).format(amount)}',
          style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.green),
        ),
      ),
    );
  }

  Widget _detailTile(IconData icon, String title, String value) {
    return Card(
      child: ListTile(
        leading: Icon(icon, color: AirwayColors.primary),
        title: Text(title),
        trailing: Text(value, textAlign: TextAlign.end, overflow: TextOverflow.ellipsis),
      ),
    );
  }

  Widget _sectionHeading(String title, {String? action, VoidCallback? onAction}) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(title, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.bold)),
        if (action != null)
          TextButton(onPressed: onAction, child: Text(action)),
      ],
    );
  }

  String _dateLabel(dynamic value) {
    if (value == null || value.toString().isEmpty) return 'Date not available';
    final parsed = DateTime.tryParse(value.toString());
    if (parsed == null) return 'Date not available';
    return DateFormat('dd MMM, hh:mm a').format(parsed.toLocal());
  }
}

class _EmptyCard extends StatelessWidget {
  const _EmptyCard({
    required this.icon,
    required this.title,
    required this.subtitle,
  });

  final IconData icon;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          children: [
            Icon(icon, size: 34, color: AirwayColors.textSecondary),
            const SizedBox(height: 10),
            Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 4),
            Text(subtitle, textAlign: TextAlign.center,
                style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12)),
          ],
        ),
      ),
    );
  }
}

class _SectionErrorCard extends StatelessWidget {
  const _SectionErrorCard({
    required this.message,
    required this.onRetry,
  });

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: const Icon(Icons.cloud_off_outlined, color: Colors.orange),
        title: const Text('This section could not be loaded'),
        subtitle: Text(message, maxLines: 3, overflow: TextOverflow.ellipsis),
        trailing: IconButton(
          tooltip: 'Retry',
          onPressed: onRetry,
          icon: const Icon(Icons.refresh),
        ),
      ),
    );
  }
}
