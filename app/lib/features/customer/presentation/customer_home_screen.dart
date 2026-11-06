import 'dart:async';
import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart' as ll;
import 'dart:ui' show ImageFilter;
import 'package:airway/core/storage/secure_session_storage.dart';
import 'package:airway/features/location/data/location_api.dart';
import 'package:airway/features/location/presentation/address_picker_screen.dart';
import 'package:airway/features/location/presentation/location_selection_screen.dart';
import 'package:airway/features/welcome/presentation/welcome_screen.dart';
import 'package:airway/features/booking/presentation/booking_list_screen.dart';
import 'package:airway/features/booking/presentation/service_detail_screen.dart';
import 'package:airway/features/notification/presentation/notification_list_screen.dart';
import 'package:airway/features/ratings/presentation/ratings_screen.dart';
import 'package:airway/features/wallet/presentation/wallet_screen.dart';
import 'package:airway/features/worker/presentation/worker_application_screen.dart';
import 'package:airway/features/worker/presentation/worker_dashboard_screen.dart';
import 'package:airway/features/worker/data/worker_app_api.dart';
import 'package:airway/features/catalog/data/catalog_api.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';
import 'package:airway/features/catalog/presentation/service_categories_screen.dart';
import 'package:airway/features/catalog/presentation/service_list_screen.dart';
import 'package:airway/features/catalog/presentation/service_detail_screen.dart' as catalog;

// AIRway customer home. Addresses and nearby online partners use authenticated APIs.
// Service cards and sample prices remain previews until the catalog API is connected.
class _Ui {
  static const violet = Color(0xFF075B43);
  static const ink = Color(0xFF17231E);
  static const sub = Color(0xFF77827C);
  static const bg = Color(0xFFF7F9F7);
  static const pale = Color(0xFFE7F1EC);
  static const line = Color(0xFFE2EAE5);
}

class _Service {
  const _Service(this.name, this.icon, this.tint, this.description);
  final String name;
  final IconData icon;
  final Color tint;
  final String description;
}

const _services = <_Service>[
  _Service('Men’s Grooming', Icons.content_cut_rounded, Color(0xFF357BDD), 'Haircuts, beard care and grooming'),
  _Service('Women’s Beauty', Icons.spa_rounded, Color(0xFFE24B9A), 'Salon and beauty care at home'),
  _Service('Home Cleaning', Icons.cleaning_services_rounded, Color(0xFF0F9F91), 'Kitchen, bathroom and deep cleaning'),
  _Service('Electrician', Icons.electrical_services_rounded, Color(0xFFED981B), 'Switches, fittings and electrical repairs'),
  _Service('Painting', Icons.format_paint_rounded, Color(0xFFE86B50), 'Painting and wall touch-ups'),
  _Service('Civil Work', Icons.handyman_rounded, Color(0xFF8263DA), 'Repairs, masonry and installations'),
  _Service('Car Wash', Icons.local_car_wash_rounded, Color(0xFF2A99DB), 'Exterior and interior cleaning'),
  _Service('Mechanical', Icons.build_circle_rounded, Color(0xFF65758A), 'Equipment and household repairs'),
  _Service('Tiffin', Icons.lunch_dining_rounded, Color(0xFFE26C38), 'Fresh home-style meal services'),
];

class CustomerHomeScreen extends StatefulWidget {
  const CustomerHomeScreen({super.key});
  @override
  State<CustomerHomeScreen> createState() => _CustomerHomeScreenState();
}

class _CustomerHomeScreenState extends State<CustomerHomeScreen> {
  List<Map<String, dynamic>> _addresses = [];
  List<Category> _catalogCategories = [];
  List<Service> _popularCatalogServices = [];
  bool _catalogLoading = false;
  String? _catalogError;
  bool _loading = true;
  String? _error;
  int _tab = 0;
  String _query = '';
  String _customerName = 'there';
  List<Map<String, dynamic>> _nearbyWorkers = [];
  bool _workersLoading = false;
  String? _workersError;
  String? _workersMessage;
  final _search = TextEditingController();
  final _searchFocus = FocusNode();
  final _offers = PageController(viewportFraction: 0.94);
  Timer? _offerTimer;
  int _offerIndex = 0;

  Map<String, dynamic>? _workerProfile;
  String? _workerStatus;
  String? _workerRejectionReason;

  @override
  void initState() {
    super.initState();
    _refresh();
    _offerTimer = Timer.periodic(const Duration(seconds: 5), (_) {
      if (!mounted || !_offers.hasClients || _tab != 0 || _query.isNotEmpty) return;
      final next = (_offerIndex + 1) % 3;
      _offers.animateToPage(next, duration: const Duration(milliseconds: 480), curve: Curves.easeInOutCubic);
    });
  }

  @override
  void dispose() {
    _offerTimer?.cancel();
    _offers.dispose();
    _search.dispose();
    _searchFocus.dispose();
    super.dispose();
  }

  Map<String, dynamic>? get _active {
    for (final a in _addresses) {
      if (a['is_default'] == true) return a;
    }
    return _addresses.isEmpty ? null : _addresses.first;
  }

  Future<void> _refresh() async {
    if (mounted) setState(() { _loading = true; _error = null; });
    try {
      final result = await LocationApi.request('/api/v1/auth/addresses/');
      final raw = result is List ? result : (result is Map ? result['results'] : null);
      if (raw is! List) throw const FormatException('Unexpected address response');
      final list = raw.map((e) => Map<String, dynamic>.from(e as Map)).toList();
      if (mounted) setState(() => _addresses = list);
      await _loadCustomerName();
      Map<String, dynamic>? selected;
      for (final savedAddress in list) {
        if (savedAddress['is_default'] == true) {
          selected = savedAddress;
          break;
        }
      }
      selected ??= list.isEmpty ? null : list.first;
      final addressId = selected?['id'];
      if (addressId != null) {
        await _loadCatalog(int.tryParse(addressId.toString()));
        await _loadNearbyWorkers(addressId.toString());
      } else if (mounted) {
        await _loadCatalog(null);
        setState(() {
          _nearbyWorkers = [];
          _workersLoading = false;
          _workersError = null;
          _workersMessage = null;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _error = 'Could not load your addresses. Check the connection and retry.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _loadCatalog(int? addressId) async {
    if (mounted) {
      setState(() {
        _catalogLoading = true;
        _catalogError = null;
        // Never keep the previous city's catalog visible while a new one loads.
        _catalogCategories = [];
        _popularCatalogServices = [];
      });
    }
    try {
      final results = await Future.wait([
        CatalogApi.listCategories(addressId: addressId),
        CatalogApi.listServices(popular: true, addressId: addressId),
      ]);
      if (!mounted) return;
      setState(() {
        _catalogCategories = results[0] as List<Category>;
        _popularCatalogServices = results[1] as List<Service>;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _catalogError = e.toString());
    } finally {
      if (mounted) setState(() => _catalogLoading = false);
    }
  }

  void _openCatalogCategory(Category category, int? addressId) {
    _searchFocus.unfocus();
    if (category.children.isNotEmpty) {
      Navigator.push<void>(
        context,
        MaterialPageRoute(
          builder: (_) => ServiceCategoriesScreen(
            initialCategories: category.children,
            addressId: addressId,
            title: category.title,
          ),
        ),
      );
      return;
    }
    Navigator.push<void>(
      context,
      MaterialPageRoute(
        builder: (_) => ServiceListScreen(
          categoryId: category.id,
          categoryTitle: category.title,
          addressId: addressId,
        ),
      ),
    );
  }

  void _openCatalogService(Service service, int? addressId) {
    _searchFocus.unfocus();
    Navigator.push<void>(
      context,
      MaterialPageRoute(
        builder: (_) => catalog.ServiceDetailScreen(
          serviceId: service.id,
          addressId: addressId,
        ),
      ),
    );
  }

  Future<void> _loadCustomerName() async {
    try {
      final response = await LocationApi.request('/api/v1/auth/me/');
      if (!mounted || response is! Map) return;
      final data = response['user'] is Map
          ? Map<String, dynamic>.from(response['user'] as Map)
          : Map<String, dynamic>.from(response);
      final fullName = '${data['full_name'] ?? data['name'] ?? ''}'.trim();
      final firstName = '${data['first_name'] ?? ''}'.trim();
      final username = '${data['username'] ?? ''}'.trim();
      final name = fullName.isNotEmpty
          ? fullName
          : firstName.isNotEmpty
              ? firstName
              : username;
      if (name.isNotEmpty) {
        setState(() => _customerName = name.split(RegExp(r'\s+')).first);
      }

      // Load worker profile status
      final workerProfile = response['worker_profile'];
      if (workerProfile is Map) {
        setState(() {
          _workerProfile = Map<String, dynamic>.from(workerProfile);
          _workerStatus = workerProfile['status'] as String?;
          _workerRejectionReason = workerProfile['rejection_reason'] as String?;
        });
      }
    } catch (_) {
      // The home screen remains usable if the profile endpoint is temporarily unavailable.
    }
  }

  Future<void> _loadNearbyWorkers(String addressId) async {
    if (mounted) {
      setState(() {
        _workersLoading = true;
        _workersError = null;
      });
    }
    try {
      final response = await LocationApi.request(
        '/api/v1/workers/nearby/?address_id=$addressId',
      );
      final raw = response is List
          ? response
          : response is Map
              ? response['results']
              : null;
      if (raw is! List) throw const FormatException('Unexpected worker response');
      final workers = raw
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
      final message = response is Map ? response['message']?.toString() : null;
      if (mounted) setState(() {
        _nearbyWorkers = workers;
        _workersMessage = message;
      });
    } catch (_) {
      if (mounted) setState(() {
        _nearbyWorkers = [];
        _workersError = 'Nearby partner availability could not be loaded.';
        _workersMessage = null;
      });
    } finally {
      if (mounted) setState(() => _workersLoading = false);
    }
  }

  void _showMessage(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _startVoiceSearch() async {
    _showMessage('Voice search is not available. Use the text search instead.');
  }

  void _showNotificationsInfo() {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (context) => const NotificationListScreen()),
    );
  }

  void _showWalletInfo() {
    showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('AIRway Wallet'),
        content: const Text(
          'Your real balance will appear here after wallet transactions, refunds and payment records are connected. No balance has been added yet.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Close')),
        ],
      ),
    );
  }

  void _showReferralInfo() {
    showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Invite & Earn'),
        content: const Text(
          'Referral tracking and rewards will activate after the referral rules and wallet ledger are connected. No reward is being promised or credited yet.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Got it')),
        ],
      ),
    );
  }

  Future<void> _switchToWorkerMode() async {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Switching to Worker mode...')),
    );
    try {
      await WorkerAppApi.switchToWorkerMode(accessToken: (await SecureSessionStorage.readSession())?.accessToken ?? '');
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Successfully switched to Worker mode!')),
      );
      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => const WorkerDashboardScreen()),
        (route) => false,
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to switch mode: $e')),
      );
    }
  }

  void _goToWorkerApplication() {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const WorkerApplicationScreen()),
    );
  }

  void _viewWorkerStatus() {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const WorkerApplicationScreen()),
    );
  }

  Future<void> _selectAddress() async {
    final current = _active;
    final latitude = double.tryParse('${current?['latitude']}') ?? 24.93;
    final longitude = double.tryParse('${current?['longitude']}') ?? 75.59;
    final result = await Navigator.of(context).push<AddressPickerResult>(
      MaterialPageRoute(builder: (_) => AddressPickerScreen(mapCenter: ll.LatLng(latitude, longitude))),
    );
    if (!mounted) return;
    if (result?.location != null) {
      await Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => LocationSelectionScreen(initialLocation: result!.location)),
      );
    }
    if (mounted) await _refresh();
  }

  Future<void> _logout() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('Log out?'),
        content: const Text('You can sign in again using your mobile number.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Log out')),
        ],
      ),
    );
    if (ok != true) return;
    await SecureSessionStorage.clearSession();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(MaterialPageRoute(builder: (_) => const WelcomeScreen()), (_) => false);
  }

  void _openService(_Service s) {
    _searchFocus.unfocus();
    Navigator.push<void>(
      context,
      MaterialPageRoute(
        builder: (_) => ServiceDetailScreen(
          serviceId: _services.indexOf(s) + 1,
          serviceTitle: s.name,
        ),
      ),
    );
  }

  void _openServiceOld(_Service s) {
    _searchFocus.unfocus();
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      backgroundColor: Colors.white,
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(22, 8, 22, 24),
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            Container(width: 70, height: 70, decoration: BoxDecoration(color: s.tint.withAlpha(25), borderRadius: BorderRadius.circular(23)),
                child: Icon(s.icon, size: 36, color: s.tint)),
            const SizedBox(height: 14),
            Text(s.name, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 24, color: _Ui.ink)),
            const SizedBox(height: 6),
            Text(s.description, style: const TextStyle(color: _Ui.sub, fontSize: 15)),
            const SizedBox(height: 16),
            const Text('Service packages and confirmed prices will appear when the AIRway catalog is published for your area.',
                style: TextStyle(color: _Ui.sub, height: 1.5)),
            const SizedBox(height: 20),
            SizedBox(width: double.infinity, child: FilledButton(
              onPressed: () => Navigator.pop(ctx), child: const Text('Continue exploring'),
            )),
          ]),
        ),
      ),
    );
  }

  void _showBeautyOptions() {
    _searchFocus.unfocus();
    showGeneralDialog<void>(
      context: context,
      barrierDismissible: true,
      barrierLabel: 'Close beauty options',
      barrierColor: Colors.black38,
      transitionDuration: const Duration(milliseconds: 320),
      pageBuilder: (dialogContext, animation, secondaryAnimation) => BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 7, sigmaY: 7),
        child: Center(
          child: Material(
            color: Colors.transparent,
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 410),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: Container(
                  padding: const EdgeInsets.all(22),
                  decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(30)),
                  child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Row(children: [
                      const Expanded(child: Text('Beauty at Home', style: TextStyle(fontSize: 24, fontWeight: FontWeight.w900, color: _Ui.ink))),
                      IconButton(onPressed: () => Navigator.pop(dialogContext), icon: const Icon(Icons.close_rounded)),
                    ]),
                    const Text('Choose a category to explore', style: TextStyle(color: _Ui.sub)),
                    const SizedBox(height: 18),
                    _beautyOption(dialogContext, _services[0], 'Men', Icons.face_rounded),
                    const SizedBox(height: 12),
                    _beautyOption(dialogContext, _services[1], 'Women', Icons.spa_rounded),
                  ]),
                ),
              ),
            ),
          ),
        ),
      ),
      transitionBuilder: (context, animation, secondaryAnimation, child) => FadeTransition(
        opacity: animation,
        child: ScaleTransition(scale: Tween<double>(begin: 0.83, end: 1).animate(CurvedAnimation(parent: animation, curve: Curves.easeOutBack)), child: child),
      ),
    );
  }

  Widget _beautyOption(BuildContext dialogContext, _Service service, String title, IconData icon) => Material(
    color: service.tint.withAlpha(16),
    borderRadius: BorderRadius.circular(20),
    child: InkWell(
      borderRadius: BorderRadius.circular(20),
      onTap: () {
        Navigator.pop(dialogContext);
        WidgetsBinding.instance.addPostFrameCallback((_) { if (mounted) _openService(service); });
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 18),
        child: Row(children: [
          CircleAvatar(radius: 26, backgroundColor: Colors.white, child: Icon(icon, color: service.tint, size: 26)),
          const SizedBox(width: 15),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: _Ui.ink)),
            Text(service.description, maxLines: 2, style: const TextStyle(color: _Ui.sub, fontSize: 12)),
          ])),
          const Icon(Icons.arrow_forward_ios_rounded, size: 17, color: _Ui.violet),
        ]),
      ),
    ),
  );

  void _openAllServices() {
    _searchFocus.unfocus();
    Navigator.push<void>(
      context,
      MaterialPageRoute(
        builder: (_) => ServiceCategoriesScreen(
          initialCategories: _catalogCategories.isEmpty ? null : _catalogCategories,
          addressId: int.tryParse('${_active?['id']}'),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final active = _active;
    return Scaffold(
      backgroundColor: _Ui.bg,
      bottomNavigationBar: NavigationBar(
        height: 70,
        backgroundColor: Colors.white,
        indicatorColor: _Ui.pale,
        selectedIndex: _tab,
        onDestinationSelected: (i) { _searchFocus.unfocus(); setState(() { _tab = i; }); },
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home_rounded, color: _Ui.violet), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.calendar_month_outlined), selectedIcon: Icon(Icons.calendar_month_rounded, color: _Ui.violet), label: 'My Bookings'),
          NavigationDestination(icon: Icon(Icons.person_outline_rounded), selectedIcon: Icon(Icons.person_rounded, color: _Ui.violet), label: 'Profile'),
        ],
      ),
      body: SafeArea(
        child: _loading
            ? _skeleton()
            : _error != null
                ? _status(Icons.wifi_off_rounded, _error!, 'Retry', _refresh)
                : active == null
                    ? _status(Icons.add_location_alt_outlined, 'Add a service address to get started.', 'Choose location', _selectAddress)
                    : IndexedStack(index: _tab, children: [
                        _home(active),
                        _bookings(),
                        _profile(active),
                      ]),
      ),
    );
  }

  Widget _status(IconData icon, String message, String action, VoidCallback callback) =>
      Center(child: Padding(padding: const EdgeInsets.all(28), child: Column(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon, color: _Ui.violet, size: 52),
        const SizedBox(height: 14),
        Text(message, textAlign: TextAlign.center, style: const TextStyle(color: _Ui.sub, height: 1.5)),
        const SizedBox(height: 16),
        FilledButton(onPressed: callback, child: Text(action)),
      ])));

  Widget _skeleton() => ListView(padding: const EdgeInsets.all(20), children: [
    for (final h in [60.0, 170.0, 56.0, 24.0, 260.0, 120.0, 150.0]) ...[
      _PulseBlock(height: h), const SizedBox(height: 18),
    ],
  ]);

  Widget _home(Map<String, dynamic> address) {
    final addressId = int.tryParse('${address['id']}');
    final query = _query.trim().toLowerCase();
    final matchingCategories = _catalogCategories.where((category) {
      return category.title.toLowerCase().contains(query) ||
          category.titleHi?.toLowerCase().contains(query) == true ||
          category.children.any((child) =>
              child.title.toLowerCase().contains(query));
    }).toList();

    return RefreshIndicator(
      onRefresh: _refresh,
      color: _Ui.violet,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.only(bottom: 30),
        children: [
          _purpleHeader(address),
          if (_query.isEmpty) ...[
            _offerCarousel(),
            _sectionHeading(
              'Service Categories',
              onSeeAll: _openAllServices,
            ),
            _categoryStrip(addressId),
            _sectionHeading(
              'Popular Services',
              onSeeAll: _openAllServices,
            ),
            _popularStrip(addressId),
            _walletReferralCard(),
            _nearbyWorkersSection(),
            _trustStrip(),
          ] else ...[
            _heading(
              'Search Results',
              '${matchingCategories.length} matching categories',
            ),
            if (_catalogLoading)
              const Padding(
                padding: EdgeInsets.all(24),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (matchingCategories.isEmpty)
              const Padding(
                padding: EdgeInsets.all(24),
                child: Text(
                  'No matching categories. Try another search.',
                  style: TextStyle(color: _Ui.sub),
                ),
              )
            else
              _dynamicCategoryGrid(matchingCategories, addressId),
          ],
          if (_catalogError != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 0),
              child: Text(
                'Catalog could not be refreshed: $_catalogError',
                style: const TextStyle(color: Colors.redAccent, fontSize: 11),
              ),
            ),
        ],
      ),
    );
  }

  Widget _purpleHeader(Map<String, dynamic> a) {
    final label = '${a['label'] ?? 'Home'}';
    final full = '${a['house_details'] ?? ''}, ${a['full_address'] ?? ''}'.replaceFirst(RegExp(r'^,\s*'), '').trim();
    final hour = DateTime.now().hour;
    final greeting = hour < 12 ? 'Morning' : hour < 17 ? 'Afternoon' : 'Evening';
    return Container(
      color: _Ui.bg,
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 18),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.location_on_rounded, color: _Ui.violet, size: 22),
          const SizedBox(width: 8),
          Expanded(child: InkWell(
            onTap: _selectAddress,
            borderRadius: BorderRadius.circular(8),
            child: Padding(padding: const EdgeInsets.symmetric(vertical: 5), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Text(label, style: const TextStyle(color: _Ui.ink, fontSize: 13, fontWeight: FontWeight.w800)),
                const Icon(Icons.keyboard_arrow_down_rounded, color: _Ui.ink, size: 18),
              ]),
              Text(full.isEmpty ? 'Choose your service address' : full, maxLines: 1, overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: _Ui.sub, fontSize: 11.5)),
            ])),
          )),
          IconButton(tooltip: 'Notifications', onPressed: _showNotificationsInfo,
            icon: const Icon(Icons.notifications_none_rounded, color: _Ui.ink, size: 25)),
        ]),
        const SizedBox(height: 18),
        Text('Good $greeting, ${_customerName == 'there' ? 'there' : _customerName}!',
          style: const TextStyle(color: _Ui.ink, fontSize: 25, fontWeight: FontWeight.w900, height: 1.15)),
        const SizedBox(height: 5),
        const Text('What service do you need today?', style: TextStyle(color: _Ui.sub, fontSize: 13)),
        const SizedBox(height: 16),
        Row(children: [
          Expanded(child: _searchBar()),
          const SizedBox(width: 10),
          Material(color: _Ui.violet, borderRadius: BorderRadius.circular(16), child: InkWell(
            borderRadius: BorderRadius.circular(16), onTap: _openAllServices,
            child: const SizedBox(width: 52, height: 52, child: Icon(Icons.tune_rounded, color: Colors.white, size: 23)),
          )),
        ]),
      ]),
    );
  }

  Widget _sectionHeading(String title, {required VoidCallback onSeeAll}) => Padding(
    padding: const EdgeInsets.fromLTRB(20, 22, 20, 12),
    child: Row(children: [
      Expanded(child: Text(title, style: const TextStyle(
        color: _Ui.ink, fontSize: 16, fontWeight: FontWeight.w900,
      ))),
      TextButton(
        onPressed: onSeeAll,
        style: TextButton.styleFrom(
          foregroundColor: _Ui.violet,
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 4),
          minimumSize: Size.zero,
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        ),
        child: const Text('See All', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w800)),
      ),
    ]),
  );

  Widget _categoryStrip(int? addressId) {
    if (_catalogLoading && _catalogCategories.isEmpty) {
      return const SizedBox(
        height: 96,
        child: Center(child: CircularProgressIndicator()),
      );
    }
    if (_catalogCategories.isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: Text(
          _catalogError == null
              ? 'No services are available in this area yet.'
              : 'Could not load categories. Pull down to retry.',
          style: const TextStyle(color: _Ui.sub, fontSize: 12),
        ),
      );
    }

    return SizedBox(
      height: 104,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 20),
        itemCount: _catalogCategories.length,
        separatorBuilder: (_, __) => const SizedBox(width: 10),
        itemBuilder: (context, index) {
          final category = _catalogCategories[index];
          return SizedBox(
            width: 76,
            child: InkWell(
              borderRadius: BorderRadius.circular(14),
              onTap: () => _openCatalogCategory(category, addressId),
              child: Column(
                children: [
                  Container(
                    width: 58,
                    height: 58,
                    clipBehavior: Clip.antiAlias,
                    decoration: BoxDecoration(
                      color: _Ui.pale,
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: _Ui.line),
                    ),
                    child: category.image?.isNotEmpty == true
                        ? Image.network(
                            category.image!,
                            fit: BoxFit.cover,
                            errorBuilder: (_, __, ___) => const Icon(
                              Icons.design_services_rounded,
                              color: _Ui.violet,
                            ),
                          )
                        : const Icon(
                            Icons.design_services_rounded,
                            color: _Ui.violet,
                          ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    category.title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      color: _Ui.ink,
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _dynamicCategoryGrid(
    List<Category> categories,
    int? addressId,
  ) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: GridView.builder(
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        itemCount: categories.length,
        gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: 2,
          mainAxisExtent: 150,
          mainAxisSpacing: 12,
          crossAxisSpacing: 12,
        ),
        itemBuilder: (context, index) {
          final category = categories[index];
          return Material(
            color: Colors.white,
            borderRadius: BorderRadius.circular(18),
            child: InkWell(
              borderRadius: BorderRadius.circular(18),
              onTap: () => _openCatalogCategory(category, addressId),
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: category.image?.isNotEmpty == true
                          ? Image.network(
                              category.image!,
                              fit: BoxFit.contain,
                              errorBuilder: (_, __, ___) => const Icon(
                                Icons.design_services_rounded,
                                color: _Ui.violet,
                                size: 34,
                              ),
                            )
                          : const Icon(
                              Icons.design_services_rounded,
                              color: _Ui.violet,
                              size: 34,
                            ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      category.title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: _Ui.ink,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    Text(
                      category.children.isEmpty
                          ? 'View services'
                          : '${category.children.length} subcategories',
                      style: const TextStyle(
                        color: _Ui.sub,
                        fontSize: 11,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _categoryTile(
    String title,
    IconData icon,
    VoidCallback onTap, {
    String? image,
    bool selected = false,
  }) => SizedBox(
    width: 66,
    child: Padding(
      padding: const EdgeInsets.only(right: 9),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: Column(children: [
          Container(
            width: 54,
            height: 54,
            clipBehavior: Clip.antiAlias,
            decoration: BoxDecoration(
              color: selected ? _Ui.pale : const Color(0xFFF0F4F1),
              borderRadius: BorderRadius.circular(13),
              border: Border.all(color: selected ? _Ui.violet : _Ui.line),
            ),
            child: image == null
              ? Icon(icon, color: _Ui.violet, size: 27)
              : Image.network(image, fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => Icon(icon, color: _Ui.violet, size: 27)),
          ),
          const SizedBox(height: 6),
          Text(title, maxLines: 1, overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
            style: const TextStyle(color: _Ui.ink, fontSize: 10, fontWeight: FontWeight.w700)),
        ]),
      ),
    ),
  );

    Widget _walletReferralCard() => Padding(
    padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
    child: Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: _Ui.line),
        boxShadow: [BoxShadow(color: _Ui.violet.withAlpha(12), blurRadius: 16, offset: const Offset(0, 5))],
      ),
      child: Column(children: [
        Row(children: [
          Container(width: 46, height: 46, decoration: BoxDecoration(color: _Ui.pale, borderRadius: BorderRadius.circular(15)),
            child: const Icon(Icons.account_balance_wallet_outlined, color: _Ui.violet, size: 25)),
          const SizedBox(width: 12),
          const Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('AIRway Wallet', style: TextStyle(color: _Ui.ink, fontSize: 15, fontWeight: FontWeight.w900)),
            SizedBox(height: 3),
            Text('Your balance and transactions', style: TextStyle(color: _Ui.sub, fontSize: 11.5)),
          ])),
          TextButton(onPressed: () {
            Navigator.of(context).push(
              MaterialPageRoute(builder: (context) => const WalletScreen()),
            );
          }, child: const Text('View')),
        ]),
        Padding(padding: const EdgeInsets.symmetric(vertical: 13), child: Divider(height: 1, color: _Ui.line)),
        Row(children: [
          Container(width: 46, height: 46, decoration: BoxDecoration(color: const Color(0xFFFFF0F8), borderRadius: BorderRadius.circular(15)),
            child: const Icon(Icons.card_giftcard_rounded, color: Color(0xFFD94691), size: 25)),
          const SizedBox(width: 12),
          const Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('Invite friends & earn', style: TextStyle(color: _Ui.ink, fontSize: 15, fontWeight: FontWeight.w900)),
            SizedBox(height: 3),
            Text('Referral rewards are being prepared', style: TextStyle(color: _Ui.sub, fontSize: 11.5)),
          ])),
          OutlinedButton(onPressed: _showReferralInfo, style: OutlinedButton.styleFrom(
            foregroundColor: _Ui.violet, side: const BorderSide(color: _Ui.violet), padding: const EdgeInsets.symmetric(horizontal: 12),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(13)),
          ), child: const Text('Invite')),
        ]),
      ]),
    ),
  );

  Widget _nearbyWorkersSection() => Padding(
    padding: const EdgeInsets.only(top: 4),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _heading('Available Partners Near You', 'Verified workers currently online in your service zone'),
      if (_workersLoading)
        const Padding(padding: EdgeInsets.fromLTRB(20, 4, 20, 8), child: LinearProgressIndicator(minHeight: 3))
      else if (_workersError != null)
        Padding(padding: const EdgeInsets.symmetric(horizontal: 20), child: Row(children: [
          const Expanded(child: Text('Partner availability could not be loaded.', style: TextStyle(color: _Ui.sub, fontSize: 12))),
          TextButton(onPressed: () { final id = _active?['id']; if (id != null) _loadNearbyWorkers(id.toString()); }, child: const Text('Retry')),
        ]))
      else if (_nearbyWorkers.isEmpty)
        Padding(padding: const EdgeInsets.fromLTRB(20, 0, 20, 4), child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(18), border: Border.all(color: _Ui.line)),
          child: Row(children: [
            const Icon(Icons.support_agent_rounded, color: _Ui.violet, size: 30),
            const SizedBox(width: 12),
            Expanded(child: Text(_workersMessage ?? 'No verified partners are online in this service zone right now. Availability updates when approved workers go online.',
              style: const TextStyle(color: _Ui.sub, fontSize: 12, height: 1.4))),
          ]),
        ))
      else
        SizedBox(height: 150, child: ListView.separated(
          padding: const EdgeInsets.symmetric(horizontal: 20),
          scrollDirection: Axis.horizontal,
          itemCount: _nearbyWorkers.length,
          separatorBuilder: (_, __) => const SizedBox(width: 12),
          itemBuilder: (context, index) {
            final worker = _nearbyWorkers[index];
            final services = worker['services'] is List ? (worker['services'] as List).map((e) => e.toString()).join(' · ') : 'Home services';
            final rating = double.tryParse('${worker['rating'] ?? ''}');
            return Container(width: 215, padding: const EdgeInsets.all(14), decoration: BoxDecoration(
              color: Colors.white, borderRadius: BorderRadius.circular(20), border: Border.all(color: _Ui.line),
            ), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                CircleAvatar(backgroundColor: _Ui.pale, child: const Icon(Icons.person_rounded, color: _Ui.violet)),
                const SizedBox(width: 9),
                Expanded(child: Text('${worker['name'] ?? 'Verified partner'}', maxLines: 1, overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: _Ui.ink, fontWeight: FontWeight.w800, fontSize: 13))),
              ]),
              const SizedBox(height: 10),
              Row(children: [
                Container(width: 7, height: 7, decoration: const BoxDecoration(color: Color(0xFF20B779), shape: BoxShape.circle)),
                const SizedBox(width: 5),
                const Text('Online', style: TextStyle(color: Color(0xFF159A64), fontSize: 11, fontWeight: FontWeight.w800)),
                if (rating != null && rating > 0) ...[
                  const Spacer(), const Icon(Icons.star_rounded, size: 15, color: Color(0xFFFFB020)),
                  Text(rating.toStringAsFixed(1), style: const TextStyle(color: _Ui.ink, fontSize: 11, fontWeight: FontWeight.w700)),
                ],
              ]),
              const Spacer(),
              Text(services, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(color: _Ui.sub, fontSize: 11.5, height: 1.25)),
            ]));
          },
        )),
    ]),
  );

  Widget _searchBar() => TextField(
    controller: _search, focusNode: _searchFocus, textInputAction: TextInputAction.search,
    onChanged: (v) => setState(() => _query = v),
    decoration: InputDecoration(
      hintText: 'Search services…',
      hintStyle: const TextStyle(fontSize: 12.5, color: _Ui.sub),
      prefixIcon: const Icon(Icons.search_rounded, color: _Ui.sub),
      suffixIcon: _query.isEmpty
        ? IconButton(tooltip: 'Search by voice', onPressed: _startVoiceSearch, icon: const Icon(Icons.mic_none_rounded, color: _Ui.sub))
        : IconButton(tooltip: 'Clear search', onPressed: () { _search.clear(); _searchFocus.unfocus(); setState(() => _query = ''); },
            icon: const Icon(Icons.close_rounded, size: 19, color: _Ui.sub)),
      filled: true, fillColor: Colors.white,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide.none),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide(color: _Ui.line)),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: const BorderSide(color: _Ui.violet, width: 1.3)),
      contentPadding: const EdgeInsets.symmetric(vertical: 15),
    ),
  );

    Widget _heading(String title, String subtitle) => Padding(
    padding: const EdgeInsets.fromLTRB(20, 26, 20, 13),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(title, style: const TextStyle(fontSize: 21, fontWeight: FontWeight.w900, color: _Ui.ink)),
      const SizedBox(height: 3),
      Text(subtitle, style: const TextStyle(fontSize: 12.5, color: _Ui.sub)),
    ]),
  );

  // Prices below are sample UI illustrations, not published AIRway rates.
  Widget _categoryGrid(List<_Service> items, {bool featured = false, bool allServices = false}) =>
      Padding(padding: EdgeInsets.symmetric(horizontal: allServices ? 0 : 20),
        child: LayoutBuilder(builder: (context, box) {
          final columns = box.maxWidth < 290 ? 1 : 2;
          return GridView.builder(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: items.length,
            gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: columns, mainAxisExtent: 192, mainAxisSpacing: 13, crossAxisSpacing: 13,
            ),
            itemBuilder: (context, i) {
              final s = items[i];
              final isBeauty = s.name == 'Women’s Beauty' || s.name == 'Men’s Grooming';
              final title = featured && isBeauty ? 'Beauty at Home' : s.name;
              final price = switch (s.name) {
                'Home Cleaning' => ('₹599', '₹799'),
                'Electrician' => ('₹99', '₹149'),
                'Women’s Beauty' => ('₹299', '₹399'),
                'Car Wash' => ('₹249', '₹349'),
                _ => ('View rates', ''),
              };
              return Material(
                color: Colors.white, borderRadius: BorderRadius.circular(23),
                child: InkWell(
                  borderRadius: BorderRadius.circular(23),
                  onTap: isBeauty ? _showBeautyOptions : () => _openService(s),
                  child: Padding(padding: const EdgeInsets.all(13), child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(children: [
                        Container(width: 60, height: 60,
                          decoration: BoxDecoration(color: s.tint.withAlpha(24), borderRadius: BorderRadius.circular(20)),
                          child: Icon(s.icon, color: s.tint, size: 32)),
                        const Spacer(),
                        Icon(Icons.arrow_outward_rounded, size: 18, color: s.tint),
                      ]),
                      const SizedBox(height: 12),
                      Text(title, maxLines: 1, overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w900, color: _Ui.ink)),
                      const SizedBox(height: 4),
                      Expanded(child: Text(s.description, maxLines: 2, overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 11.5, height: 1.25, color: _Ui.sub))),
                      Row(children: [
                        Flexible(child: Text(price.$1, maxLines: 1, overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w900, color: _Ui.violet))),
                        if (price.$2.isNotEmpty) ...[
                          const SizedBox(width: 6),
                          Flexible(child: Text(price.$2, maxLines: 1, overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontSize: 11, decoration: TextDecoration.lineThrough, color: _Ui.sub))),
                        ],
                      ]),
                    ],
                  )),
                ),
              );
            },
          );
        }),
      );

  Widget _trustStrip() => Padding(padding: const EdgeInsets.fromLTRB(20, 20, 20, 0), child: Container(
    decoration: BoxDecoration(color: _Ui.pale, borderRadius: BorderRadius.circular(20)),
    padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 5),
    child: Row(children: [
      _trustItem(Icons.location_on_outlined, 'Local focus'),
      _trustItem(Icons.receipt_long_outlined, 'Clear pricing'),
      _trustItem(Icons.support_agent_outlined, 'Support'),
    ]),
  ));

  Widget _trustItem(IconData icon, String title) => Expanded(child: Column(mainAxisSize: MainAxisSize.min, children: [
    Icon(icon, color: _Ui.violet, size: 25), const SizedBox(height: 6),
    Text(title, textAlign: TextAlign.center, maxLines: 2, style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: _Ui.ink)),
  ]));

  Widget _emptyBookings() => Padding(padding: const EdgeInsets.symmetric(horizontal: 20), child: Container(
    padding: const EdgeInsets.all(17), decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(22)),
    child: Row(children: [
      Container(width: 55, height: 55, decoration: BoxDecoration(color: _Ui.pale, borderRadius: BorderRadius.circular(18)),
          child: const Icon(Icons.history_rounded, color: _Ui.violet, size: 29)),
      const SizedBox(width: 13),
      const Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('Your favorites will appear here', style: TextStyle(color: _Ui.ink, fontWeight: FontWeight.w800, fontSize: 13.5)),
        SizedBox(height: 5),
        Text('After your first completed booking, you can quickly book again.',
            style: TextStyle(color: _Ui.sub, fontSize: 12, height: 1.3)),
      ])),
    ]),
  ));

  Widget _popularStrip(int? addressId) {
    if (_catalogLoading && _popularCatalogServices.isEmpty) {
      return const SizedBox(
        height: 190,
        child: Center(child: CircularProgressIndicator()),
      );
    }
    if (_popularCatalogServices.isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: Text(
          'Popular services will appear here when they are published for this area.',
          style: const TextStyle(color: _Ui.sub, fontSize: 12),
        ),
      );
    }

    return SizedBox(
      height: 190,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 20),
        itemCount: _popularCatalogServices.length,
        separatorBuilder: (_, __) => const SizedBox(width: 12),
        itemBuilder: (context, index) {
          final service = _popularCatalogServices[index];
          final price = service.variants.isNotEmpty
              ? service.variants.first.price
              : service.visitFee;
          return SizedBox(
            width: 164,
            child: Material(
              color: Colors.white,
              borderRadius: BorderRadius.circular(16),
              clipBehavior: Clip.antiAlias,
              child: InkWell(
                onTap: () => _openCatalogService(service, addressId),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(
                      height: 112,
                      width: double.infinity,
                      child: service.image?.isNotEmpty == true
                          ? Image.network(
                              service.image!,
                              fit: BoxFit.cover,
                              errorBuilder: (_, __, ___) => Container(
                                color: _Ui.pale,
                                child: const Icon(
                                  Icons.home_repair_service_rounded,
                                  color: _Ui.violet,
                                  size: 42,
                                ),
                              ),
                            )
                          : Container(
                              color: _Ui.pale,
                              child: const Icon(
                                Icons.home_repair_service_rounded,
                                color: _Ui.violet,
                                size: 42,
                              ),
                            ),
                    ),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(10, 9, 8, 7),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            service.title,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              color: _Ui.ink,
                              fontSize: 12,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                          const SizedBox(height: 3),
                          Text(
                            price > 0
                                ? 'From ₹${price.toStringAsFixed(0)}'
                                : service.categoryName,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              color: _Ui.sub,
                              fontSize: 10,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }

    Widget _offerCarousel() {
    const captions = ['Clean Spaces,', 'Repairs Made', 'Care at Your'];
    const secondLines = ['Happier Days', 'Simple', 'Doorstep'];
    const subtitles = ['A cleaner home starts here', 'Reliable help for everyday fixes', 'Home services made easy'];
    const icons = [Icons.cleaning_services_rounded, Icons.handyman_rounded, Icons.home_repair_service_rounded];
    const colors = [Color(0xFF075B43), Color(0xFF0C6B4D), Color(0xFF174F3D)];
    const images = [
      'https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?auto=format&fit=crop&w=1100&q=85',
      'https://images.unsplash.com/photo-1581578731548-c64695cc6952?auto=format&fit=crop&w=1100&q=85',
      'https://images.unsplash.com/photo-1600210492486-724fe5c67fb0?auto=format&fit=crop&w=1100&q=85',
    ];
    return Column(children: [
      SizedBox(height: 174, child: PageView.builder(
        controller: _offers, itemCount: 3, onPageChanged: (v) => setState(() => _offerIndex = v),
        itemBuilder: (context, i) => Padding(padding: const EdgeInsets.symmetric(horizontal: 20), child: Material(
          color: colors[i], borderRadius: BorderRadius.circular(22), clipBehavior: Clip.antiAlias,
          child: InkWell(onTap: _openAllServices,
            child: Stack(fit: StackFit.expand, children: [
              Image.network(images[i], fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => Container(color: colors[i])),
              DecoratedBox(decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [const Color(0xE6003D2C), const Color(0xA6003D2C), Colors.transparent],
                  begin: Alignment.centerLeft, end: Alignment.centerRight,
                ),
              )),
              Padding(padding: const EdgeInsets.fromLTRB(19, 17, 12, 15), child: Row(children: [
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisAlignment: MainAxisAlignment.center, children: [
                  Text(captions[i], style: const TextStyle(color: Colors.white, fontSize: 19, fontWeight: FontWeight.w800)),
                  Text(secondLines[i], style: const TextStyle(color: Colors.white, fontSize: 19, fontWeight: FontWeight.w900)),
                  const SizedBox(height: 6),
                  Text(subtitles[i], maxLines: 2, style: TextStyle(color: Colors.white.withAlpha(235), fontSize: 11.5)),
                  const SizedBox(height: 11),
                  Container(padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                    decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(10)),
                    child: const Text('Book Now', style: TextStyle(color: _Ui.violet, fontSize: 11.5, fontWeight: FontWeight.w800))),
                ])),
                const SizedBox(width: 8),
              ])),
            ]),
          ),
        )),
      )),
      const SizedBox(height: 10),
      Row(mainAxisAlignment: MainAxisAlignment.center, children: List.generate(3, (i) => AnimatedContainer(
        duration: const Duration(milliseconds: 260), width: i == _offerIndex ? 21 : 7, height: 7,
        margin: const EdgeInsets.symmetric(horizontal: 3),
        decoration: BoxDecoration(color: i == _offerIndex ? _Ui.violet : _Ui.line, borderRadius: BorderRadius.circular(9)),
      ))),
    ]);
  }

    Widget _bookings() => const BookingListScreen();

  Widget _bookingsOld() => RefreshIndicator(
    onRefresh: _refresh,
    child: ListView(physics: const AlwaysScrollableScrollPhysics(), padding: const EdgeInsets.all(24), children: [
      const Text('My Bookings', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w900, color: _Ui.ink)),
      const SizedBox(height: 60),
      const Icon(Icons.calendar_month_outlined, size: 72, color: _Ui.violet),
      const SizedBox(height: 16),
      const Text('Bookings are coming soon', textAlign: TextAlign.center,
          style: TextStyle(fontSize: 19, fontWeight: FontWeight.w800, color: _Ui.ink)),
      const SizedBox(height: 8),
      const Text('Your real booking history will show here when booking is enabled.', textAlign: TextAlign.center,
          style: TextStyle(color: _Ui.sub, height: 1.5)),
      const SizedBox(height: 20),
      Center(child: OutlinedButton(onPressed: () => setState(() => _tab = 0), child: const Text('Explore services'))),
    ]),
  );

  Widget _profile(Map<String, dynamic> address) => ListView(padding: const EdgeInsets.all(20), children: [
    const Text('Profile', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w900, color: _Ui.ink)),
    const SizedBox(height: 16),
    Container(padding: const EdgeInsets.all(20), decoration: BoxDecoration(color: _Ui.pale, borderRadius: BorderRadius.circular(22)),
      child: Row(children: [
        const CircleAvatar(radius: 24, backgroundColor: Colors.white, child: Icon(Icons.person_outline, color: _Ui.violet)),
        const SizedBox(width: 12),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Your AIRway account', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w800, color: _Ui.ink)),
          Text('${_addresses.length} saved addresses', style: const TextStyle(color: _Ui.sub)),
        ])),
      ]),
    ),
    const SizedBox(height: 16),

    // Worker profile status card
    if (_workerProfile != null) ...[
      _buildWorkerStatusCard(),
      const SizedBox(height: 16),
    ],

    // Become a Worker button (shown when not approved as worker)
    if (_workerProfile == null || (_workerStatus != 'approved' && _workerStatus != 'rejected')) ...[
      Card(
        color: Colors.white,
        elevation: 2,
        child: ListTile(
          leading: const Icon(Icons.work, color: _Ui.violet),
          title: const Text('Become a Worker'),
          subtitle: const Text('Earn money providing services in your area'),
          trailing: const Icon(Icons.chevron_right),
          onTap: _goToWorkerApplication,
        ),
      ),
      const SizedBox(height: 8),
    ],

    Card(color: Colors.white, elevation: 0, child: Column(children: [
      ListTile(leading: const Icon(Icons.location_on_outlined, color: _Ui.violet), title: const Text('Manage addresses'),
          subtitle: Text('${address['full_address'] ?? ''}', maxLines: 1, overflow: TextOverflow.ellipsis),
          trailing: const Icon(Icons.chevron_right), onTap: _selectAddress),
      const Divider(height: 1, indent: 16, endIndent: 16),
      ListTile(leading: const Icon(Icons.account_balance_wallet_outlined, color: _Ui.violet), title: const Text('Wallet'),
          subtitle: const Text('View balance and transactions'),
          trailing: const Icon(Icons.chevron_right),
          onTap: () {
            Navigator.of(context).push(
              MaterialPageRoute(builder: (context) => const WalletScreen()),
            );
          }),
      const Divider(height: 1, indent: 16, endIndent: 16),
      ListTile(leading: const Icon(Icons.refresh, color: _Ui.violet), title: const Text('Refresh account data'), onTap: _refresh),
      const Divider(height: 1, indent: 16, endIndent: 16),
      ListTile(leading: const Icon(Icons.rate_review_rounded, color: _Ui.violet), title: const Text('My Ratings'),
          subtitle: const Text('Rate your service providers'),
          trailing: const Icon(Icons.chevron_right),
          onTap: () {
            Navigator.of(context).push(
              MaterialPageRoute(builder: (context) => const RatingsScreen()),
            );
          }),
      const Divider(height: 1, indent: 16, endIndent: 16),
      ListTile(leading: const Icon(Icons.logout_rounded, color: _Ui.violet), title: const Text('Log out'), onTap: _logout),
    ])),
  ]);

  Widget _buildWorkerStatusCard() {
    final status = _workerStatus ?? 'no_profile';
    final isApproved = status == 'approved';
    final isPending = status == 'pending';
    final isRejected = status == 'rejected';

    Color cardColor;
    Color iconColor;
    IconData statusIcon;
    String statusText;

    if (isApproved) {
      cardColor = Colors.green[50]!;
      iconColor = Colors.green;
      statusIcon = Icons.check_circle;
      statusText = 'Approved Worker';
    } else if (isPending) {
      cardColor = Colors.orange[100]!;
      iconColor = Colors.orange;
      statusIcon = Icons.pending_actions;
      statusText = 'Application Pending';
    } else if (isRejected) {
      cardColor = Colors.red[100]!;
      iconColor = Colors.red;
      statusIcon = Icons.cancel;
      statusText = 'Application Rejected';
    } else {
      cardColor = _Ui.pale;
      iconColor = _Ui.violet;
      statusIcon = Icons.work_outline;
      statusText = 'Not registered as Worker';
    }

    return Card(
      color: cardColor,
      elevation: 2,
      child: ListTile(
        leading: Icon(statusIcon, color: iconColor, size: 28),
        title: Text(
          isApproved ? 'Switch to Worker Mode' : statusText,
          style: TextStyle(fontWeight: FontWeight.w800, color: iconColor),
        ),
        subtitle: isApproved
            ? const Text('You can accept jobs as a verified worker')
            : isPending
                ? const Text('Awaiting admin verification')
                : isRejected
                    ? Text(_workerRejectionReason?.isNotEmpty == true
                        ? 'Reason: $_workerRejectionReason'
                        : 'Your application was not approved')
                    : const Text('Register to earn by providing services'),
        trailing: isApproved
            ? Switch(
                value: true,
                onChanged: (_) => _switchToWorkerMode(),
              )
            : isRejected
                ? TextButton(
                    onPressed: _viewWorkerStatus,
                    child: const Text('Reapply'),
                  )
                : IconButton(
                    icon: const Icon(Icons.chevron_right),
                    onPressed: _goToWorkerApplication,
                  ),
      ),
    );
  }
}

class _PulseBlock extends StatefulWidget {
  const _PulseBlock({required this.height});
  final double height;
  @override
  State<_PulseBlock> createState() => _PulseBlockState();
}

class _PulseBlockState extends State<_PulseBlock> with SingleTickerProviderStateMixin {
  late final AnimationController _animation = AnimationController(
    vsync: this, duration: const Duration(milliseconds: 1100),
  )..repeat(reverse: true);
  @override
  void dispose() { _animation.dispose(); super.dispose(); }
  @override
  Widget build(BuildContext context) => AnimatedBuilder(animation: _animation, builder: (context, _) => Container(
    height: widget.height, decoration: BoxDecoration(
      color: Color.lerp(const Color(0xFFE9E5F3), const Color(0xFFF6F3FA), _animation.value),
      borderRadius: BorderRadius.circular(21),
    ),
  ));
}
