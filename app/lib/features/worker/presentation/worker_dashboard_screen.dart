import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:intl/intl.dart';
import 'package:airway/core/network/auth_api.dart';

import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/core/storage/secure_session_storage.dart';
import 'package:airway/features/welcome/presentation/welcome_screen.dart';
import 'package:airway/features/customer/presentation/customer_home_screen.dart';
import 'package:airway/features/worker/data/worker_app_api.dart';
import 'package:airway/features/worker/data/worker_api.dart';
import 'package:airway/features/worker/data/worker_models.dart';
import 'package:airway/features/worker/presentation/assigned_job_screen.dart';
import 'package:airway/features/worker/presentation/job_offers_screen.dart';
import 'package:airway/features/worker/presentation/worker_profile_edit_screen.dart';
import 'package:airway/features/worker/presentation/worker_leave_screen.dart';
import 'package:airway/features/worker/presentation/worker_service_management_screen.dart';
import 'package:airway/features/notification/data/push_notification_service.dart';
import 'package:airway/features/notification/presentation/notification_bell_button.dart';
import 'package:airway/features/account/presentation/account_profile_screen.dart';
import 'package:airway/features/account/presentation/notification_preferences_screen.dart';
import 'package:airway/features/account/presentation/account_preferences_screen.dart';
import 'package:airway/features/account/presentation/account_deletion_screen.dart';
import 'package:airway/core/localization/airway_locale.dart';
import 'package:airway/core/localization/airway_text.dart';
import 'package:airway/features/account/presentation/legal_documents_screen.dart';
import 'package:airway/features/account/presentation/account_security_screen.dart';
import 'package:airway/features/account/presentation/help_support_screen.dart';

class WorkerDashboardScreen extends StatefulWidget {
  const WorkerDashboardScreen({super.key});

  @override
  State<WorkerDashboardScreen> createState() => _WorkerDashboardScreenState();
}

class _WorkerDashboardScreenState extends State<WorkerDashboardScreen> with WidgetsBindingObserver {
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
  Timer? _offerPollTimer;
  final Set<int> _knownOfferIds = {};
  final Set<int> _offerActionsInProgress = {};
  bool _incomingOfferDialogOpen = false;
  StreamSubscription<RemoteMessage>? _pushOpenSubscription;
  StreamSubscription<RemoteMessage>? _pushForegroundSubscription;

  static const _tabTitles = ['Home', 'Jobs', 'Earnings', 'Profile'];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    PushNotificationService.initializeForAuthenticatedUser().catchError((_) {});
    _pushOpenSubscription = FirebaseMessaging.onMessageOpenedApp.listen(_handlePushOpen);
    _pushForegroundSubscription = FirebaseMessaging.onMessage.listen(_handlePushOpen);
    FirebaseMessaging.instance.getInitialMessage().then((message) {
      if (message != null) _handlePushOpen(message);
    });
    _loadDashboard().then((_) {
      _knownOfferIds.addAll(_offers.map((offer) => offer.id));
      _startOfferPolling();
      final recentOffers = _offers.where((offer) =>
          offer.status == WorkerOffer.pending &&
          (offer.expiresAt == null || offer.expiresAt!.isAfter(DateTime.now())) &&
          DateTime.now().difference(offer.offeredAt).abs() <= const Duration(minutes: 5)).toList();
      if (recentOffers.isNotEmpty) _showIncomingOffer(recentOffers.first);
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _offerPollTimer?.cancel();
    _pushOpenSubscription?.cancel();
    _pushForegroundSubscription?.cancel();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _pollNewOffers();
  }

  Future<void> _handlePushOpen(RemoteMessage message) async {
    if (message.data['notification_kind'] != 'worker_offer' || !mounted) return;
    final offerId = int.tryParse(message.data['offer_id']?.toString() ?? '');
    try {
      final latest = await WorkerApi.getJobOffers();
      if (!mounted) return;
      setState(() => _offers = latest);
      final matching = latest.where((item) =>
          item.id == offerId && item.status == WorkerOffer.pending).toList();
      if (matching.isNotEmpty) {
        await _showIncomingOffer(matching.first);
      } else {
        _openOffers();
      }
    } catch (_) {
      if (mounted) _openOffers();
    }
  }

  void _startOfferPolling() {
    _offerPollTimer?.cancel();
    _offerPollTimer = Timer.periodic(const Duration(seconds: 15), (_) => _pollNewOffers());
  }

  Future<void> _pollNewOffers() async {
    if (!mounted || WidgetsBinding.instance.lifecycleState != AppLifecycleState.resumed) return;
    try {
      final latest = await WorkerApi.getJobOffers();
      if (!mounted) return;
      final incoming = latest.where((offer) =>
          offer.status == WorkerOffer.pending && !_knownOfferIds.contains(offer.id)).toList();
      _knownOfferIds.addAll(latest.map((offer) => offer.id));
      setState(() => _offers = latest);
      if (incoming.isNotEmpty && !_incomingOfferDialogOpen) {
        _showIncomingOffer(incoming.first);
      }
    } catch (_) {
      // Keep the dashboard usable if a background refresh temporarily fails.
    }
  }

  Future<void> _showIncomingOffer(WorkerOffer offer) async {
    if (!mounted || _incomingOfferDialogOpen) return;
    _incomingOfferDialogOpen = true;
    SystemSound.play(SystemSoundType.alert);
    HapticFeedback.vibrate();
    try {
      await showDialog<void>(
        context: context,
        barrierDismissible: true,
        builder: (dialogContext) => AlertDialog(
          icon: const Icon(Icons.notifications_active_rounded, size: 34, color: AirwayColors.primary),
          title: Text(AirwayText.tr('New service request', 'नई सेवा रिक्वेस्ट')),
          content: SizedBox(
            width: 420,
            child: SingleChildScrollView(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
                if (offer.serviceImageUrl?.isNotEmpty == true)
                  ClipRRect(
                    borderRadius: BorderRadius.circular(12),
                    child: Image.network(offer.serviceImageUrl!, height: 120, width: double.infinity, fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) => const SizedBox.shrink()),
                  ),
                Text(offer.serviceTitle ?? 'AIRway service', style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
                if (offer.variantTitle?.isNotEmpty == true) Text(offer.variantTitle!),
                if (offer.customerName?.trim().isNotEmpty == true)
                  Text(AirwayText.tr('Customer: ${offer.customerName}', 'ग्राहक: ${offer.customerName}')),
                if (offer.serviceDescription?.trim().isNotEmpty == true)
                  Padding(padding: const EdgeInsets.only(top: 8), child: Text(offer.serviceDescription!, style: const TextStyle(fontSize: 12, height: 1.4))),
                if (offer.orderServices.length > 1) ...[
                  const SizedBox(height: 10),
                  Text(AirwayText.tr('Services in this order', 'इस ऑर्डर की सेवाएँ'), style: TextStyle(fontWeight: FontWeight.w800)),
                  for (final item in offer.orderServices)
                    Padding(
                      padding: const EdgeInsets.only(top: 5),
                      child: Text(
                        '• ${item['service_title'] ?? 'Service'}'
                        '${item['variant_title'] == null ? '' : ' — ${item['variant_title']}'}'
                        '${item['quantity'] == null ? '' : ' × ${item['quantity']}'}'
                        '${item['scheduled_at'] == null ? '' : ' · ${_dateLabel(item['scheduled_at'])}'}',
                      ),
                    ),
                ],
                const SizedBox(height: 8),
                if (offer.scheduledAt != null) Text(AirwayText.tr('Requested time: ${_dateLabel(offer.scheduledAt)}', 'अनुरोधित समय: ${_dateLabel(offer.scheduledAt)}')),
                if (offer.serviceAddress?.isNotEmpty == true) Text(AirwayText.tr('Address: ${offer.serviceAddress}', 'पता: ${offer.serviceAddress}')),
                Text(AirwayText.tr('Quantity: ${offer.quantity}', 'मात्रा: ${offer.quantity}')),
                for (final entry in offer.customerAnswers.entries)
                  Text(workerCustomerAnswerLabel(entry.key, entry.value)),
                for (final answer in offer.formResponses)
                  Text('${answer['label'] ?? answer['key']}: ${answer['value']}'),
                if (offer.addons.isNotEmpty)
                  Text(AirwayText.tr('Add-ons: ${offer.addons.map((item) => item['title']).join(', ')}', 'अतिरिक्त सेवाएँ: ${offer.addons.map((item) => item['title']).join(', ')}')),
                const SizedBox(height: 8),
                Text(AirwayText.tr('Review the details before accepting. AIRway will confirm the assignment with the server.', 'स्वीकार करने से पहले विवरण जाँचें। AIRway सर्वर से असाइनमेंट की पुष्टि करेगा।'), style: TextStyle(fontSize: 12)),
              ]),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.pop(dialogContext);
                _openOffers();
              },
              child: Text(AirwayText.tr('View later', 'बाद में देखें')),
            ),
            TextButton(
              onPressed: () async {
                Navigator.pop(dialogContext);
                try {
                  await WorkerApi.declineOffer(offer.id);
                  if (mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(AirwayText.tr('Request declined.', 'रिक्वेस्ट अस्वीकार कर दी गई।'))));
                    await _refresh();
                  }
                } catch (e) {
                  if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(AirwayText.tr('Could not decline request: $e', 'रिक्वेस्ट अस्वीकार नहीं हो सकी: $e'))));
                }
              },
              child: Text(AirwayText.tr('Reject', 'अस्वीकार करें')),
            ),
            FilledButton(
              onPressed: () async {
                Navigator.pop(dialogContext);
                try {
                  await WorkerApi.acceptOffer(offer.id);
                  if (mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(AirwayText.tr('Request accepted. Assignment confirmed.', 'रिक्वेस्ट स्वीकार हो गई। असाइनमेंट कन्फ़र्म है।'))));
                    await _refresh();
                    _openAssignedJobs();
                  }
                } catch (e) {
                  if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(AirwayText.tr('Request could not be accepted: $e', 'रिक्वेस्ट स्वीकार नहीं हो सकी: $e'))));
                  await _refresh();
                }
              },
              child: Text(AirwayText.tr('Accept service', 'सेवा स्वीकार करें')),
            ),
          ],
        ),
      );
    } finally {
      _incomingOfferDialogOpen = false;
    }
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
            photoUrl: _profile!.photoUrl,
            serviceItems: _profile!.serviceItems,
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
          SnackBar(content: Text(AirwayText.tr('Could not update availability: $e', 'उपलब्धता अपडेट नहीं हो सकी: $e'))),
        );
      }
    } finally {
      if (mounted) setState(() => _availabilitySaving = false);
    }
  }

  Future<void> _editProfile() async {
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => WorkerProfileEditScreen(profile: _profile!)),
    );
    if (changed == true) await _refresh();
  }

  Future<void> _editAccountProfile() async {
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => const AccountProfileScreen(workerMode: true)),
    );
    if (changed == true) await _refresh();
  }

  Future<void> _openNotificationPreferences() async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute(builder: (_) => const NotificationPreferencesScreen()),
    );
  }

  Future<void> _manageServices() async {
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => WorkerServiceManagementScreen(profile: _profile!)),
    );
    if (changed == true) await _refresh();
  }

  String? _photoUrl(WorkerProfile profile) {
    final raw = profile.photoUrl;
    if (raw == null || raw.trim().isEmpty) return null;
    return Uri.parse(AuthApi.baseUrl).resolve(raw).toString();
  }

  Future<void> _switchToCustomerMode() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(AirwayText.tr('Switch to Customer?', 'कस्टमर मोड पर जाएँ?')),
        content: Text(AirwayText.tr('You will return to Customer Home using this same account. Your worker profile and job history will remain saved.', 'आप इसी खाते से कस्टमर होम पर लौटेंगे। आपकी वर्कर प्रोफ़ाइल और जॉब हिस्ट्री सुरक्षित रहेगी।')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: Text(AirwayText.tr('Cancel', 'रद्द करें'))),
          FilledButton(onPressed: () => Navigator.pop(dialogContext, true), child: Text(AirwayText.tr('Switch', 'बदलें'))),
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
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(AirwayText.tr('Could not switch to Customer mode: $e', 'कस्टमर मोड पर नहीं जा सके: $e'))));
    }
  }

  Future<void> _endSession({required bool switchAccount}) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(switchAccount ? 'Switch account?' : 'Log out?'),
        content: Text(switchAccount ? 'You will be signed out so another AIRway account can sign in on this device.' : 'You will be securely signed out of AIRway.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: Text(AirwayText.tr('Cancel', 'रद्द करें'))),
          FilledButton(onPressed: () => Navigator.pop(dialogContext, true), child: Text(switchAccount ? 'Continue' : 'Log out')),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await PushNotificationService.unregisterCurrentDevice();
    } catch (_) {
      // Session cleanup must still complete if the push service is unavailable.
    }
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
        appBar: AppBar(title: Text(AirwayText.tr('Worker Dashboard', 'वर्कर डैशबोर्ड'))),
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
                  label: Text(AirwayText.tr('Try again', 'फिर कोशिश करें')),
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
          const NotificationBellButton(),
          IconButton(
            tooltip: AirwayText.tr('Refresh', 'रीफ़्रेश करें'),
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
    final pendingOffers = _offers.where((o) => o.status == WorkerOffer.pending).toList();
    final activeJobs = _assignedJobs.where((j) {
      final status = j['status']?.toString();
      return status != 'completed' && status != 'cancelled';
    }).toList();

    return _page([
      _buildWelcomeCard(profile),
      const SizedBox(height: 12),
      _buildAvailabilityCard(profile),
      const SizedBox(height: 22),
      Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(
            child: Text(
              AirwayText.tr('New service requests', 'नई सर्विस रिक्वेस्ट'),
              style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w900),
            ),
          ),
          if (pendingOffers.isNotEmpty)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
              decoration: BoxDecoration(
                color: AirwayColors.primary.withValues(alpha: 0.10),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Text(
                '${pendingOffers.length} NEW',
                style: const TextStyle(color: AirwayColors.primary, fontSize: 11, fontWeight: FontWeight.w900),
              ),
            ),
          TextButton(onPressed: _openOffers, child: Text(AirwayText.tr('See all', 'सभी देखें'))),
        ],
      ),
      const SizedBox(height: 4),
      if (_offersError != null)
        _SectionErrorCard(message: _offersError!, onRetry: _refresh)
      else if (pendingOffers.isEmpty)
        const _EmptyCard(
          icon: Icons.inbox_outlined,
          title: 'No new service requests',
          subtitle: 'When a customer books one of your services, the request will appear here. Keep your availability on to receive offers.',
        )
      else
        ...pendingOffers.take(3).map(_buildOfferPreview),
      const SizedBox(height: 22),
      Row(
        children: [
          Expanded(child: _buildMetricCard('New requests', '${pendingOffers.length}', Icons.notifications_active_outlined)),
          const SizedBox(width: 10),
          Expanded(child: _buildMetricCard('Active jobs', '${activeJobs.length}', Icons.assignment_outlined)),
        ],
      ),
      const SizedBox(height: 22),
      _sectionHeading(
        AirwayText.tr('Your active work', 'आपका चालू काम'),
        action: AirwayText.tr('View jobs', 'जॉब देखें'),
        onAction: _openAssignedJobs,
      ),
      const SizedBox(height: 8),
      if (_jobsError != null)
        _SectionErrorCard(message: _jobsError!, onRetry: _refresh)
      else if (activeJobs.isEmpty)
        const _EmptyCard(
          icon: Icons.work_outline_rounded,
          title: 'No active jobs yet',
          subtitle: 'Once you accept a service request, its details and next steps will appear here.',
        )
      else
        ...activeJobs.take(3).map(_buildJobPreview),
      const SizedBox(height: 18),
      _sectionHeading(
        AirwayText.tr('Your next steps', 'आपके अगले कदम'),
        action: AirwayText.tr('Open profile', 'प्रोफ़ाइल खोलें'),
        onAction: () => setState(() => _selectedTab = 3),
      ),
      const SizedBox(height: 8),
      _buildNextJobCard(),
    ]);
  }

  Widget _buildJobsTab() {
    final active = _assignedJobs.where((j) => j['status']?.toString() != 'completed' && j['status']?.toString() != 'cancelled').toList();
    final completed = _assignedJobs.where((j) => j['status']?.toString() == 'completed').toList();
    final pendingOffers = _offers.where((o) => o.status == WorkerOffer.pending).toList();

    return _page([
      Row(
        children: [
          Expanded(child: Text(AirwayText.tr('New service requests', 'नई सर्विस रिक्वेस्ट'), style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w900))),
          if (pendingOffers.isNotEmpty)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
              decoration: BoxDecoration(color: AirwayColors.primary.withValues(alpha: 0.10), borderRadius: BorderRadius.circular(20)),
              child: Text('${pendingOffers.length} NEW', style: const TextStyle(color: AirwayColors.primary, fontSize: 11, fontWeight: FontWeight.w900)),
            ),
        ],
      ),
      const SizedBox(height: 8),
      if (_offersError != null)
        _SectionErrorCard(message: _offersError!, onRetry: _refresh)
      else if (pendingOffers.isEmpty)
        const _EmptyCard(icon: Icons.inbox_outlined, title: 'No new service requests', subtitle: 'New customer requests for your enrolled services will appear here.')
      else
        ...pendingOffers.map(_buildOfferPreview),
      const SizedBox(height: 22),
      _sectionHeading(AirwayText.tr('Assigned work', 'आपको सौंपे गए काम'), action: AirwayText.tr('Open all', 'सभी खोलें'), onAction: _openAssignedJobs),
      const SizedBox(height: 8),
      if (_jobsError != null)
        _SectionErrorCard(message: _jobsError!, onRetry: _refresh)
      else if (active.isEmpty)
        const _EmptyCard(icon: Icons.work_outline_rounded, title: 'No active jobs', subtitle: 'Jobs you accept will appear here. Open a job to see customer details and update its progress.')
      else
        ...active.map(_buildJobPreview),
      if (completed.isNotEmpty) ...[
        const SizedBox(height: 18),
        Text(AirwayText.tr('Completed jobs: ${completed.length}', 'पूरे किए गए काम: ${completed.length}'), style: const TextStyle(fontWeight: FontWeight.w700)),
      ],
    ]);
  }

  Widget _buildEarningsTab() {
    double totalFor(String status, [String amountKey = 'net_amount']) => _earnings
        .where((item) => item['status'] == status)
        .fold<double>(
          0,
          (sum, item) => sum + (double.tryParse('${item[amountKey]?.toString() ?? ''}') ?? 0),
        );
    final available = totalFor('available');
    final pending = totalFor('pending');
    final onHold = totalFor('on_hold', 'gross_amount');
    final paid = totalFor('paid');
    String money(double value) => NumberFormat.currency(
      locale: 'en_IN', symbol: '₹', decimalDigits: 0,
    ).format(value);

    return _page([
      Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [Color(0xFF6C4AE3), Color(0xFF4D32B5)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              AirwayText.tr('Available for payout', 'भुगतान के लिए उपलब्ध'),
              style: const TextStyle(color: Colors.white70, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 7),
            Text(
              money(available),
              style: const TextStyle(color: Colors.white, fontSize: 32, fontWeight: FontWeight.w900),
            ),
            const SizedBox(height: 5),
            Text(
              AirwayText.tr('Only settled and approved earnings are included', 'केवल सेटल और स्वीकृत कमाई शामिल है'),
              style: const TextStyle(color: Colors.white70, fontSize: 12),
            ),
          ],
        ),
      ),
      const SizedBox(height: 12),
      Row(children: [
        Expanded(child: _earningSummaryCard('Pending', pending, Icons.hourglass_top_rounded, const Color(0xFFB7791F))),
        const SizedBox(width: 10),
        Expanded(child: _earningSummaryCard('Gross on hold', onHold, Icons.pause_circle_outline_rounded, const Color(0xFFB45309))),
      ]),
      const SizedBox(height: 10),
      _earningSummaryCard('Paid out', paid, Icons.check_circle_outline_rounded, AirwayColors.success),
      const SizedBox(height: 10),
      Container(
        padding: const EdgeInsets.all(13),
        decoration: BoxDecoration(
          color: const Color(0xFFFBFAFF),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: const Color(0xFFE8E2F5)),
        ),
        child: Row(children: [
          const Icon(Icons.account_balance_outlined, color: Color(0xFF6C4AE3)),
          const SizedBox(width: 10),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('Payout account', style: TextStyle(fontWeight: FontWeight.w800)),
            Text(
              _profile?.upiId?.trim().isNotEmpty == true
                  ? _profile!.upiId!
                  : 'Add your UPI ID in Profile settings',
              style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12),
            ),
          ])),
          TextButton(onPressed: _editProfile, child: const Text('Edit')),
        ]),
      ),
      const SizedBox(height: 22),
      Text(
        AirwayText.tr('Earning history', 'कमाई का इतिहास'),
        style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w900),
      ),
      const SizedBox(height: 8),
      if (_earningsError != null)
        _SectionErrorCard(message: _earningsError!, onRetry: _refresh)
      else if (_earnings.isEmpty)
        const _EmptyCard(
          icon: Icons.account_balance_wallet_outlined,
          title: 'No settled earnings yet',
          subtitle: 'Your verified earnings will appear here after the customer payment is settled.',
        )
      else
        ..._earnings.map(_buildEarningRow),
      const SizedBox(height: 8),
      Text(
        'Commission and payout status are controlled by AIRway finance. Amounts on hold are not available for withdrawal.',
        style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12),
      ),
    ]);
  }

  Widget _earningSummaryCard(String title, double amount, IconData icon, Color accent) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFE8E2F5)),
      ),
      child: Row(children: [
        Icon(icon, color: accent, size: 22),
        const SizedBox(width: 9),
        Expanded(child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12)),
            const SizedBox(height: 3),
            Text(
              NumberFormat.currency(locale: 'en_IN', symbol: '₹', decimalDigits: 0).format(amount),
              style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 17, color: AirwayColors.text),
            ),
          ],
        )),
      ]),
    );
  }

  Widget _buildProfileTab(WorkerProfile profile) {
    final hi = AirwayLocale.current.languageCode == 'hi';
    final t = AirwayText.tr;
    final photo = _photoUrl(profile);
    final services = profile.serviceItems;
    return _page([
      Card(
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Row(children: [
            CircleAvatar(
              radius: 34,
              backgroundColor: AirwayColors.primary.withValues(alpha: 0.12),
              backgroundImage: photo == null ? null : NetworkImage(photo),
              child: photo == null ? Icon(Icons.person_rounded, size: 38, color: AirwayColors.primary) : null,
            ),
            const SizedBox(width: 14),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(profile.name?.trim().isNotEmpty == true ? profile.name! : t('AIRway Worker', 'AIRway वर्कर'),
                  style: const TextStyle(fontSize: 19, fontWeight: FontWeight.bold)),
              Text(profile.phone ?? t('Phone not available', 'फ़ोन उपलब्ध नहीं'), style: TextStyle(color: AirwayColors.textSecondary)),
              const SizedBox(height: 5),
              Row(children: [
                const Icon(Icons.verified_rounded, size: 16, color: Colors.green),
                SizedBox(width: 4),
                Text(t('Verified worker', 'सत्यापित वर्कर'), style: TextStyle(color: Colors.green, fontWeight: FontWeight.w700, fontSize: 12)),
              ]),
            ])),
            IconButton(tooltip: t('Edit profile', 'प्रोफ़ाइल संपादित करें'), onPressed: _editProfile, icon: const Icon(Icons.edit_outlined)),
          ]),
        ),
      ),
      const SizedBox(height: 12),
      Card(
        child: Column(children: [
          ListTile(
            leading: const Icon(Icons.category_outlined),
            title: Text(t('My services', 'मेरी सेवाएँ'), style: TextStyle(fontWeight: FontWeight.w800)),
            subtitle: Text(t('${services.length} services selected', '${services.length} सेवाएँ चुनी गईं')),
            trailing: const Icon(Icons.chevron_right_rounded),
            onTap: _manageServices,
          ),
          if (services.isNotEmpty) const Divider(height: 1),
          if (services.isNotEmpty)
            ExpansionTile(
              key: const PageStorageKey<String>('worker_dashboard_selected_services_expansion'),
              leading: const Icon(Icons.visibility_outlined),
              title: Text(t('View selected services', 'चुनी गई सेवाएँ देखें')),
              subtitle: Text(t('Expand only when you need the full list', 'पूरी सूची देखने के लिए खोलें')),
              children: services.map((item) => ListTile(
                dense: true,
                leading: const Icon(Icons.check_circle_outline, size: 18),
                title: Text(item['service_title']?.toString() ?? t('Service', 'सेवा')),
                subtitle: item['capabilities'] is List && (item['capabilities'] as List).isNotEmpty
                    ? Text((item['capabilities'] as List).join(', '), maxLines: 2, overflow: TextOverflow.ellipsis)
                    : null,
              )).toList(),
            ),
        ]),
      ),
      const SizedBox(height: 14),
      Card(
        child: Column(children: [
          ListTile(
            leading: const Icon(Icons.person_outline_rounded),
            title: Text(hi ? 'व्यक्तिगत जानकारी' : 'Personal information'),
            subtitle: Text(hi ? 'खाते का नाम, ईमेल, फोटो और पंजीकृत फ़ोन' : 'Account name, email, photo and registered phone'),
            trailing: const Icon(Icons.chevron_right_rounded),
            onTap: _editAccountProfile,
          ),
          const Divider(height: 1),
          ListTile(
            leading: const Icon(Icons.notifications_outlined),
            title: Text(hi ? 'सूचना प्राथमिकताएँ' : 'Notification preferences'),
            subtitle: Text(hi ? 'इस डिवाइस पर पुश नोटिफिकेशन नियंत्रित करें' : 'Control push notifications on this device'),
            trailing: const Icon(Icons.chevron_right_rounded),
            onTap: _openNotificationPreferences,
          ),
          const Divider(height: 1),
          ListTile(
            leading: const Icon(Icons.tune_rounded),
            title: Text(hi ? 'ऐप प्राथमिकताएँ' : 'App preferences'),
            subtitle: Text(hi ? 'भाषा सेटिंग' : 'Language settings'),
            trailing: const Icon(Icons.chevron_right_rounded),
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const AccountPreferencesScreen()),
            ),
          ),
          const Divider(height: 1),
          ListTile(
            leading: const Icon(Icons.description_outlined),
            title: Text(hi ? 'नियम और गोपनीयता' : 'Terms & Privacy'),
            subtitle: Text(hi ? 'AIRway के नियम और गोपनीयता जानकारी पढ़ें' : 'Read AIRway terms and privacy information'),
            trailing: const Icon(Icons.chevron_right_rounded),
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const LegalDocumentsScreen()),
            ),
          ),
          const Divider(height: 1),
          ListTile(
            leading: const Icon(Icons.person_off_outlined),
            title: Text(hi ? 'खाता हटाने का अनुरोध' : 'Delete account'),
            subtitle: Text(hi ? 'अपना AIRway खाता बंद करने का अनुरोध भेजें' : 'Submit a request to close your AIRway account'),
            trailing: const Icon(Icons.chevron_right_rounded),
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const AccountDeletionScreen()),
            ),
          ),
          const Divider(height: 1),
          ListTile(
            leading: const Icon(Icons.security_outlined),
            title: Text(hi ? 'पासवर्ड और सुरक्षा' : 'Password & security'),
            subtitle: Text(hi ? 'अपने खाते का पासवर्ड बदलें या सेट करें' : 'Change or set your account password'),
            trailing: const Icon(Icons.chevron_right_rounded),
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const AccountSecurityScreen()),
            ),
          ),
        ]),
      ),
      const SizedBox(height: 14),
      _sectionHeading(hi ? 'आपकी जानकारी' : 'Your details'),
      const SizedBox(height: 8),
      _detailTile(Icons.star_outline_rounded, t('Rating', 'रेटिंग'), profile.ratingAvg == null ? t('Not rated yet', 'अभी रेटिंग नहीं') : profile.ratingAvg!.toStringAsFixed(1)),
      _detailTile(Icons.work_history_outlined, t('Experience', 'अनुभव'), t('${profile.experienceYears ?? 0} years', '${profile.experienceYears ?? 0} वर्ष')),
      _detailTile(Icons.school_outlined, t('Qualification', 'योग्यता'), profile.qualification?.isNotEmpty == true ? profile.qualification! : t('Not added', 'जोड़ा नहीं गया')),
      _detailTile(Icons.home_outlined, t('Residential address', 'निवास का पता'), profile.residentialAddress?.isNotEmpty == true ? profile.residentialAddress! : t('Not added', 'जोड़ा नहीं गया')),
      _detailTile(Icons.location_on_outlined, t('Landmark', 'पहचान स्थल'), profile.landmark?.isNotEmpty == true ? profile.landmark! : t('Not added', 'जोड़ा नहीं गया')),
      _detailTile(Icons.handyman_outlined, t('Tools / equipment', 'औज़ार / उपकरण'), profile.equipmentDetails?.isNotEmpty == true ? profile.equipmentDetails! : t('Not added', 'जोड़ा नहीं गया')),
      _detailTile(Icons.payments_outlined, t('Payout UPI ID', 'भुगतान UPI ID'), profile.upiId?.isNotEmpty == true ? profile.upiId! : t('Not added', 'जोड़ा नहीं गया')),
      _detailTile(Icons.verified_user_outlined, t('Application', 'आवेदन'), t('Approved', 'स्वीकृत')),
      if (profile.bio?.isNotEmpty == true) _detailTile(Icons.person_outline_rounded, t('About your work', 'आपके काम के बारे में'), profile.bio!),
      if (profile.documents.isNotEmpty) _detailTile(
        Icons.description_outlined,
        t('Verification documents', 'सत्यापन दस्तावेज़'),
        profile.documents.map((item) {
          final type = item['doc_type']?.toString() ?? t('Document', 'दस्तावेज़');
          final status = item['status']?.toString() ?? 'pending';
          return '$type: $status';
        }).join(', '),
      ),
      if (profile.zones.isNotEmpty) _detailTile(Icons.map_outlined, t('Service areas', 'सेवा क्षेत्र'), profile.zones.join(', ')),
      if (profile.schedules.isNotEmpty) _detailTile(
        Icons.schedule_outlined,
        t('Working hours', 'कार्य समय'),
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
      const SizedBox(height: 14),
      OutlinedButton.icon(onPressed: _editProfile, icon: const Icon(Icons.edit_outlined), label: Text(t('Edit profile details', 'प्रोफ़ाइल विवरण संपादित करें'))),
      const SizedBox(height: 10),
      Card(
        child: ListTile(
          leading: const Icon(Icons.event_busy_outlined, color: AirwayColors.primary),
          title: Text(t('Leave management', 'छुट्टी प्रबंधन')),
          subtitle: Text(t('Request time off and track Admin decisions', 'छुट्टी का अनुरोध करें और एडमिन का निर्णय देखें')),
          trailing: const Icon(Icons.chevron_right_rounded),
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => const WorkerLeaveScreen()),
          ),
        ),
      ),
      const SizedBox(height: 16),
      Card(
        child: ListTile(
          leading: const Icon(Icons.support_agent_outlined),
          title: Text(hi ? 'मदद और सहायता' : 'Help & Support'),
          subtitle: Text(hi ? 'जॉब ऑफ़र, वर्क प्रोफ़ाइल और कमाई में सहायता' : 'Guidance for job offers, work profile and earnings'),
          trailing: const Icon(Icons.chevron_right_rounded),
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute(
              builder: (_) => HelpSupportScreen(
                workerMode: true,
                onPrimaryAction: () => setState(() => _selectedTab = 1),
                onSecondaryAction: () => setState(() => _selectedTab = 2),
              ),
            ),
          ),
        ),
      ),
      const SizedBox(height: 16),
      _sectionHeading(hi ? 'खाता' : 'Account'),
      Card(
        child: Column(children: [
          ListTile(leading: const Icon(Icons.account_balance_wallet_outlined), title: Text(hi ? 'कमाई और भुगतान' : 'Earnings & payouts'), subtitle: Text(hi ? 'कमाई टैब में दर्ज कमाई देखें' : 'View credited job earnings in the Earnings tab'), trailing: const Icon(Icons.chevron_right_rounded), onTap: () => setState(() => _selectedTab = 2)),
          const Divider(height: 1),
          ListTile(leading: const Icon(Icons.notifications_active_outlined), title: Text(hi ? 'जॉब अलर्ट' : 'Job alerts'), subtitle: Text(hi ? 'नई सर्विस ऑफ़र जॉब्स टैब में दिखेंगे' : 'New service offers appear in the Jobs tab'), trailing: const Icon(Icons.chevron_right_rounded), onTap: _openOffers),
          const Divider(height: 1),
          ListTile(leading: const Icon(Icons.storefront_outlined), title: Text(hi ? 'कस्टमर मोड में जाएँ' : 'Switch to Customer'), subtitle: Text(hi ? 'इसी खाते से कस्टमर होम पर लौटें' : 'Return to Customer Home with this account'), trailing: const Icon(Icons.chevron_right_rounded), onTap: _switchToCustomerMode),
          const Divider(height: 1),
          ListTile(leading: const Icon(Icons.switch_account_outlined), title: Text(hi ? 'खाता बदलें' : 'Switch Account'), subtitle: Text(hi ? 'साइन आउट करके दूसरा खाता उपयोग करें' : 'Sign out and use another account'), trailing: const Icon(Icons.chevron_right_rounded), onTap: () => _endSession(switchAccount: true)),
          const Divider(height: 1),
          ListTile(leading: Icon(Icons.logout_rounded, color: AirwayColors.error), title: Text(hi ? 'लॉग आउट' : 'Log out', style: TextStyle(color: AirwayColors.error)), subtitle: Text(hi ? 'AIRway से सुरक्षित रूप से साइन आउट करें' : 'Securely sign out of AIRway'), onTap: () => _endSession(switchAccount: false)),
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
                  Text(AirwayText.tr('Hello, ${profile.name?.trim().isNotEmpty == true ? profile.name : 'Partner'}!', 'नमस्ते, ${profile.name?.trim().isNotEmpty == true ? profile.name : 'पार्टनर'}!'),
                      style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 5),
                  Text(AirwayText.tr('Ready for your next service?', 'अपनी अगली सेवा के लिए तैयार हैं?'), style: TextStyle(color: AirwayColors.textSecondary)),
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
    final online = profile.isOnline;
    final accent = online ? const Color(0xFF21834A) : AirwayColors.textSecondary;
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 14, 12, 14),
      decoration: BoxDecoration(
        color: online ? const Color(0xFFEDF8F0) : const Color(0xFFF4F2F8),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: online ? const Color(0xFFCDEBD5) : const Color(0xFFE5E1EC)),
      ),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(color: accent.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(14)),
            child: Icon(online ? Icons.wifi_rounded : Icons.wifi_off_rounded, color: accent, size: 23),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  online ? AirwayText.tr('You are available for work', 'आप काम के लिए उपलब्ध हैं') : AirwayText.tr('You are currently offline', 'आप अभी ऑफलाइन हैं'),
                  style: TextStyle(fontWeight: FontWeight.w900, color: accent, fontSize: 14),
                ),
                const SizedBox(height: 3),
                Text(
                  online ? AirwayText.tr('New service requests can reach you', 'आपको नई सर्विस रिक्वेस्ट मिल सकती हैं') : AirwayText.tr('Turn on to receive service requests', 'सर्विस रिक्वेस्ट पाने के लिए ऑनलाइन हों'),
                  style: TextStyle(color: AirwayColors.textSecondary, fontSize: 11, height: 1.3),
                ),
              ],
            ),
          ),
          const SizedBox(width: 6),
          if (_availabilitySaving)
            const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2))
          else
            Switch.adaptive(value: online, onChanged: _toggleAvailability, activeColor: AirwayColors.primary),
        ],
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
        subtitle: Text(AirwayText.tr('Booking #${job['booking_id'] ?? job['id']} • ${_dateLabel(job['scheduled_at'])}', 'बुकिंग #${job['booking_id'] ?? job['id']} • ${_dateLabel(job['scheduled_at'])}')),
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
        subtitle: Text(AirwayText.tr('Booking #${job['booking_id'] ?? job['id']} • ${_dateLabel(job['scheduled_at'])}', 'बुकिंग #${job['booking_id'] ?? job['id']} • ${_dateLabel(job['scheduled_at'])}')),
        trailing: const Icon(Icons.chevron_right_rounded),
        onTap: () => _openAssignedJobs(assignmentId: job['id'] as int?),
      ),
    );
  }

  Future<void> _respondToOfferFromHome(WorkerOffer offer, {required bool accept}) async {
    if (_offerActionsInProgress.contains(offer.id)) return;
    setState(() => _offerActionsInProgress.add(offer.id));
    try {
      if (accept) {
        await WorkerApi.acceptOffer(offer.id);
      } else {
        await WorkerApi.declineOffer(offer.id);
      }
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(accept
            ? AirwayText.tr('Service accepted. Your job is confirmed.', 'सेवा स्वीकार हो गई। आपका काम कन्फ़र्म है।')
            : AirwayText.tr('Request rejected.', 'रिक्वेस्ट अस्वीकार कर दी गई।')),
      ));
      await _refresh();
      if (accept && mounted) _openAssignedJobs();
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(AirwayText.tr('Could not respond: $error', 'जवाब नहीं भेज सके: $error')),
      ));
      await _refresh();
    } finally {
      if (mounted) setState(() => _offerActionsInProgress.remove(offer.id));
    }
  }

  Widget _buildOfferPreview(WorkerOffer offer) {
    final serviceName = offer.serviceTitle?.trim().isNotEmpty == true
        ? offer.serviceTitle!.trim()
        : AirwayText.tr('Service request', 'सर्विस रिक्वेस्ट');
    final when = offer.scheduledAt == null
        ? AirwayText.tr('Schedule to be confirmed', 'समय की पुष्टि बाकी है')
        : _dateLabel(offer.scheduledAt);
    final address = offer.serviceAddress?.trim() ?? '';

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AirwayColors.primary.withValues(alpha: 0.24)),
        boxShadow: [
          BoxShadow(color: AirwayColors.primary.withValues(alpha: 0.06), blurRadius: 14, offset: const Offset(0, 5)),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 46,
                  height: 46,
                  decoration: BoxDecoration(color: AirwayColors.primary.withValues(alpha: 0.10), borderRadius: BorderRadius.circular(14)),
                  child: const Icon(Icons.home_repair_service_rounded, color: AirwayColors.primary, size: 25),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(serviceName, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w900, color: AirwayColors.text)),
                      const SizedBox(height: 3),
                      Text('Booking #${offer.bookingId}', style: TextStyle(fontSize: 12, color: AirwayColors.textSecondary)),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
                  decoration: BoxDecoration(color: const Color(0xFFEAF7EF), borderRadius: BorderRadius.circular(20)),
                  child: Text(AirwayText.tr('NEW', 'नई'), style: const TextStyle(color: Color(0xFF21834A), fontSize: 10, fontWeight: FontWeight.w900)),
                ),
              ],
            ),
            if (offer.serviceImageUrl?.isNotEmpty == true) ...[
              const SizedBox(height: 10),
              ClipRRect(borderRadius: BorderRadius.circular(12), child: Image.network(offer.serviceImageUrl!, height: 110, width: double.infinity, fit: BoxFit.cover, errorBuilder: (_, __, ___) => const SizedBox.shrink())),
            ],
            if (offer.variantTitle?.trim().isNotEmpty == true) ...[
              const SizedBox(height: 10),
              Text(offer.variantTitle!, style: const TextStyle(fontWeight: FontWeight.w700)),
            ],
            if (offer.customerName?.trim().isNotEmpty == true) ...[
              const SizedBox(height: 7),
              _offerInfoLine(Icons.person_outline_rounded, 'Customer: ${offer.customerName}'),
            ],
            if (offer.serviceDescription?.trim().isNotEmpty == true) ...[
              const SizedBox(height: 7),
              Text(offer.serviceDescription!, maxLines: 3, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12, height: 1.35, color: AirwayColors.textSecondary)),
            ],
            const SizedBox(height: 12),
            _offerInfoLine(Icons.calendar_month_outlined, when),
            if (address.isNotEmpty) ...[
              const SizedBox(height: 7),
              _offerInfoLine(Icons.location_on_outlined, address, maxLines: 2),
            ],
            const SizedBox(height: 7),
            _offerInfoLine(Icons.timer_outlined, '${offer.expectedDurationMinutes} min estimated service time'),
            if (offer.quantity > 1) ...[
              const SizedBox(height: 7),
              _offerInfoLine(Icons.format_list_numbered_rounded, 'Quantity: ${offer.quantity}'),
            ],
            const SizedBox(height: 14),
            if (_offerActionsInProgress.contains(offer.id))
              const Center(child: CircularProgressIndicator())
            else
              Row(children: [
                if (offer.canDecline)
                  Expanded(child: OutlinedButton.icon(
                    onPressed: () => _respondToOfferFromHome(offer, accept: false),
                    icon: const Icon(Icons.close_rounded),
                    label: Text(AirwayText.tr('Reject', 'मना करें')),
                    style: OutlinedButton.styleFrom(foregroundColor: AirwayColors.error, minimumSize: const Size.fromHeight(48)),
                  )),
                if (offer.canDecline && offer.canAccept) const SizedBox(width: 10),
                if (offer.canAccept)
                  Expanded(flex: 2, child: FilledButton.icon(
                    onPressed: () => _respondToOfferFromHome(offer, accept: true),
                    icon: const Icon(Icons.check_circle_outline_rounded),
                    label: Text(AirwayText.tr('Accept job', 'काम स्वीकार करें')),
                    style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(48)),
                  )),
              ]),
            Align(alignment: Alignment.centerRight, child: TextButton.icon(
              onPressed: _openOffers,
              icon: const Icon(Icons.open_in_new_rounded, size: 16),
              label: Text(AirwayText.tr('See full request details', 'पूरी रिक्वेस्ट देखें')),
            )),
          ],
        ),
      ),
    );
  }

  Widget _offerInfoLine(IconData icon, String value, {int maxLines = 1}) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 17, color: AirwayColors.primary),
        const SizedBox(width: 8),
        Expanded(child: Text(value, maxLines: maxLines, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 12, color: AirwayColors.textSecondary, height: 1.35))),
      ],
    );
  }

  Widget _buildEarningRow(Map<String, dynamic> item) {
    final gross = double.tryParse('${item['gross_amount']}') ?? 0;
    final commission = double.tryParse('${item['commission_amount']}') ?? 0;
    final net = double.tryParse('${item['net_amount']}') ?? 0;
    final status = item['status']?.toString() ?? 'pending';
    final statusLabel = switch (status) {
      'available' => 'Available',
      'paid' => 'Paid',
      'on_hold' => 'On hold',
      _ => 'Pending settlement',
    };
    final statusColor = switch (status) {
      'available' || 'paid' => AirwayColors.success,
      'on_hold' => const Color(0xFFB45309),
      _ => const Color(0xFF8A641B),
    };
    final title = item['service_title']?.toString().trim();
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFE8E2F5)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: Text(
            title?.isNotEmpty == true ? title! : 'Service earning',
            style: const TextStyle(fontWeight: FontWeight.w800, color: AirwayColors.text),
          )),
          Text(
            statusLabel,
            style: TextStyle(color: statusColor, fontSize: 11, fontWeight: FontWeight.w800),
          ),
        ]),
        const SizedBox(height: 5),
        Text(
          'Booking #${item['booking_id'] ?? '—'} • ${_dateLabel(item['created_at'])}',
          style: TextStyle(color: AirwayColors.textSecondary, fontSize: 11),
        ),
        const Divider(height: 18),
        _earningAmountLine(
          item['extra_work_id'] != null ? 'Approved extra-work amount' : 'Service amount',
          gross,
        ),
        if (item['commission_amount'] != null)
          _earningAmountLine(
            'AIRway commission (${item['commission_rate'] ?? '—'}%)',
            -commission,
          ),
        if ((double.tryParse('${item['adjustment_amount'] ?? '0'}') ?? 0) != 0)
          _earningAmountLine(
            'Finance adjustment',
            double.tryParse('${item['adjustment_amount']}') ?? 0,
          ),
        const SizedBox(height: 5),
        Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          const Text('Your earning', style: TextStyle(fontWeight: FontWeight.w800)),
          Text(
            item['net_amount'] == null ? 'Awaiting rate' : '₹${net.toStringAsFixed(2)}',
            style: const TextStyle(fontWeight: FontWeight.w900, color: Color(0xFF6C4AE3), fontSize: 16),
          ),
        ]),
        if ((item['adjustment_note']?.toString() ?? '').isNotEmpty) ...[
          const SizedBox(height: 6),
          Text('Finance note: ${item['adjustment_note']}', style: TextStyle(color: AirwayColors.textSecondary, fontSize: 11)),
        ],
        if ((item['hold_reason']?.toString() ?? '').isNotEmpty) ...[
          const SizedBox(height: 8),
          Text(item['hold_reason'].toString(), style: const TextStyle(color: Color(0xFFB45309), fontSize: 12)),
        ],
        if ((item['payout_reference']?.toString() ?? '').isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 5),
            child: Text('Payout reference: ${item['payout_reference']}', style: TextStyle(color: AirwayColors.textSecondary, fontSize: 11)),
          ),
      ]),
    );
  }

  Widget _earningAmountLine(String label, double amount) {
    final prefix = amount < 0 ? '-₹' : '₹';
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        Text(label, style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12)),
        Text(
          '$prefix${amount.abs().toStringAsFixed(2)}',
          style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700),
        ),
      ]),
    );
  }

  Widget _detailTile(IconData icon, String title, String value) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: AirwayColors.primary),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    title,
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 4),
                  Text(value, softWrap: true),
                ],
              ),
            ),
          ],
        ),
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
        title: Text(AirwayText.tr('This section could not be loaded', 'यह सेक्शन लोड नहीं हो सका')),
        subtitle: Text(message, maxLines: 3, overflow: TextOverflow.ellipsis),
        trailing: IconButton(
          tooltip: AirwayText.tr('Retry', 'फिर कोशिश करें'),
          onPressed: onRetry,
          icon: const Icon(Icons.refresh),
        ),
      ),
    );
  }
}
