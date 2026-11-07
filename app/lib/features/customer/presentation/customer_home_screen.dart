import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:latlong2/latlong.dart' as ll;
import 'package:airway/core/storage/secure_session_storage.dart';
import 'package:airway/features/location/data/location_api.dart';
import 'package:airway/features/location/presentation/address_picker_screen.dart';
import 'package:airway/features/location/presentation/location_selection_screen.dart';
import 'package:airway/features/welcome/presentation/welcome_screen.dart';
import 'package:airway/features/booking/presentation/booking_list_screen.dart';
import 'package:airway/features/booking/presentation/customer_cart_screen.dart';
import 'package:airway/features/notification/presentation/notification_list_screen.dart';
import 'package:airway/features/ratings/presentation/ratings_screen.dart';
import 'package:airway/features/wallet/presentation/wallet_screen.dart';
import 'package:airway/features/worker/presentation/worker_application_screen.dart';
import 'package:airway/features/worker/presentation/worker_dashboard_screen.dart';
import 'package:airway/features/worker/data/worker_app_api.dart';
import 'package:airway/features/catalog/data/catalog_api.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';
import 'package:airway/features/catalog/presentation/service_categories_screen.dart';
import 'package:airway/features/catalog/presentation/category_decision_screen.dart';
import 'package:airway/features/catalog/presentation/service_list_screen.dart';
import 'package:airway/features/catalog/presentation/service_detail_screen.dart'
    as catalog;

// AIRway customer home. Address, catalogue, pricing and nearby partners are loaded from authenticated APIs.
class _Ui {
  static const violet = Color(0xFF315C46);
  static const ink = AirwayColors.text;
  static const sub = AirwayColors.textSecondary;
  static const bg = AirwayColors.background;
  static const pale = Color(0xFFEAF1EA);
  static const line = Color(0xFFEAE6DE);
}

class CustomerHomeScreen extends StatefulWidget {
  const CustomerHomeScreen({super.key});
  @override
  State<CustomerHomeScreen> createState() => _CustomerHomeScreenState();
}

class _CustomerHomeScreenState extends State<CustomerHomeScreen> {
  List<Map<String, dynamic>> _addresses = [];
  List<Category> _catalogCategories = [];
  List<Service> _popularCatalogServices = [];
  List<CatalogBanner> _homeBanners = [];
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
  final _bannerController = PageController(viewportFraction: 0.96);

  Map<String, dynamic>? _workerProfile;
  String? _workerStatus;
  String? _workerRejectionReason;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  @override
  void dispose() {
    _search.dispose();
    _searchFocus.dispose();
    _bannerController.dispose();
    super.dispose();
  }

  Map<String, dynamic>? get _active {
    for (final a in _addresses) {
      if (a['is_default'] == true) return a;
    }
    return _addresses.isEmpty ? null : _addresses.first;
  }

  Future<void> _refresh() async {
    if (mounted)
      setState(() {
        _loading = true;
        _error = null;
      });
    try {
      final result = await LocationApi.request('/api/v1/auth/addresses/');
      final raw = result is List
          ? result
          : (result is Map ? result['results'] : null);
      if (raw is! List)
        throw const FormatException('Unexpected address response');
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
      if (mounted)
        setState(
          () => _error =
              'Could not load your addresses. Check the connection and retry.',
        );
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
        _homeBanners = [];
      });
    }
    try {
      final results = await Future.wait([
        CatalogApi.listCategories(addressId: addressId),
        CatalogApi.listServices(popular: true, addressId: addressId),
        CatalogApi.listBanners(addressId: addressId),
      ]);
      if (!mounted) return;
      setState(() {
        _catalogCategories = results[0] as List<Category>;
        _popularCatalogServices = results[1] as List<Service>;
        _homeBanners = results[2] as List<CatalogBanner>;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _catalogError = e.toString());
    } finally {
      if (mounted) setState(() => _catalogLoading = false);
    }
  }

  Future<void> _openCatalogCategory(Category category, int? addressId) async {
    _searchFocus.unfocus();
    var answers = <String, dynamic>{};
    if (category.flowSteps.isNotEmpty) {
      final selected = await Navigator.push<Map<String, dynamic>>(
        context,
        MaterialPageRoute(
          builder: (_) => CategoryDecisionScreen(
            categoryTitle: category.title,
            steps: category.flowSteps,
          ),
        ),
      );
      if (selected == null || !mounted) return;
      answers = selected;
    }
    if (category.children.isNotEmpty) {
      Navigator.push<void>(
        context,
        MaterialPageRoute(
          builder: (_) => ServiceCategoriesScreen(
            initialCategories: category.children,
            addressId: addressId,
            title: category.title,
            initialAnswers: answers,
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
          initialAnswers: answers,
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

      // Worker application state is supplied by the authenticated /me/ API.
      final workerProfile = response['worker_profile'];
      final applicationStatus = response['worker_application_status'];
      final profile = workerProfile is Map
          ? Map<String, dynamic>.from(workerProfile)
          : null;
      final application = applicationStatus is Map
          ? Map<String, dynamic>.from(applicationStatus)
          : null;
      if (mounted) {
        setState(() {
          _workerProfile = profile;
          _workerStatus =
              profile?['status']?.toString() ??
              application?['status']?.toString();
          _workerRejectionReason =
              profile?['rejection_reason']?.toString() ??
              application?['rejection_reason']?.toString();
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
      if (raw is! List)
        throw const FormatException('Unexpected worker response');
      final workers = raw
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
      final message = response is Map ? response['message']?.toString() : null;
      if (mounted)
        setState(() {
          _nearbyWorkers = workers;
          _workersMessage = message;
        });
    } catch (_) {
      if (mounted)
        setState(() {
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

  void _showReferralInfo() {
    showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Invite & Earn'),
        content: const Text(
          'Referral tracking and rewards will activate after the referral rules and wallet ledger are connected. No reward is being promised or credited yet.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Got it'),
          ),
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
      await WorkerAppApi.switchToWorkerMode(
        accessToken:
            (await SecureSessionStorage.readSession())?.accessToken ?? '',
      );
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
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Failed to switch mode: $e')));
    }
  }

  Future<void> _goToWorkerApplication() async {
    await Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => const WorkerApplicationScreen()),
    );
    if (mounted) await _refresh();
  }

  Future<void> _viewWorkerStatus() async {
    await Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => const WorkerApplicationScreen()),
    );
    if (mounted) await _refresh();
  }

  Future<void> _selectAddress() async {
    final current = _active;
    final latitude = double.tryParse('${current?['latitude']}') ?? 24.93;
    final longitude = double.tryParse('${current?['longitude']}') ?? 75.59;
    final result = await Navigator.of(context).push<AddressPickerResult>(
      MaterialPageRoute(
        builder: (_) =>
            AddressPickerScreen(mapCenter: ll.LatLng(latitude, longitude)),
      ),
    );
    if (!mounted) return;
    if (result?.location != null) {
      await Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) =>
              LocationSelectionScreen(initialLocation: result!.location),
        ),
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
          TextButton(
            onPressed: () => Navigator.pop(c, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(c, true),
            child: const Text('Log out'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    await SecureSessionStorage.clearSession();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const WelcomeScreen()),
      (_) => false,
    );
  }

  void _openAllServices() {
    _searchFocus.unfocus();
    Navigator.push<void>(
      context,
      MaterialPageRoute(
        builder: (_) => ServiceCategoriesScreen(
          initialCategories: _catalogCategories.isEmpty
              ? null
              : _catalogCategories,
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
        onDestinationSelected: (i) {
          _searchFocus.unfocus();
          setState(() {
            _tab = i;
          });
        },
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home_rounded, color: _Ui.violet),
            label: 'Home',
          ),
          NavigationDestination(
            icon: Icon(Icons.calendar_month_outlined),
            selectedIcon: Icon(Icons.calendar_month_rounded, color: _Ui.violet),
            label: 'My Bookings',
          ),
          NavigationDestination(
            icon: Icon(Icons.person_outline_rounded),
            selectedIcon: Icon(Icons.person_rounded, color: _Ui.violet),
            label: 'Profile',
          ),
        ],
      ),
      body: SafeArea(
        child: _loading
            ? _skeleton()
            : _error != null
            ? _status(Icons.wifi_off_rounded, _error!, 'Retry', _refresh)
            : active == null
            ? _status(
                Icons.add_location_alt_outlined,
                'Add a service address to get started.',
                'Choose location',
                _selectAddress,
              )
            : IndexedStack(
                index: _tab,
                children: [_home(active), _bookings(), _profile(active)],
              ),
      ),
    );
  }

  Widget _status(
    IconData icon,
    String message,
    String action,
    VoidCallback callback,
  ) => Center(
    child: Padding(
      padding: const EdgeInsets.all(28),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: _Ui.violet, size: 52),
          const SizedBox(height: 14),
          Text(
            message,
            textAlign: TextAlign.center,
            style: const TextStyle(color: _Ui.sub, height: 1.5),
          ),
          const SizedBox(height: 16),
          FilledButton(onPressed: callback, child: Text(action)),
        ],
      ),
    ),
  );

  Widget _skeleton() => ListView(
    padding: const EdgeInsets.all(20),
    children: [
      for (final h in [60.0, 170.0, 56.0, 24.0, 260.0, 120.0, 150.0]) ...[
        _PulseBlock(height: h),
        const SizedBox(height: 18),
      ],
    ],
  );

  Widget _home(Map<String, dynamic> address) {
    final addressId = int.tryParse('${address['id']}');
    final query = _query.trim().toLowerCase();
    final matchingCategories = _catalogCategories.where((category) {
      return category.title.toLowerCase().contains(query) ||
          category.titleHi?.toLowerCase().contains(query) == true ||
          category.children.any(
            (child) => child.title.toLowerCase().contains(query),
          );
    }).toList();

    return RefreshIndicator(
      onRefresh: _refresh,
      color: _Ui.violet,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.only(bottom: 30),
        children: [
          _purpleHeader(address),
          if (_workerStatus == 'pending' ||
              _workerStatus == 'approved' ||
              _workerStatus == 'rejected')
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 4),
              child: _buildWorkerHomeStatusCard(),
            ),
          if (_query.isEmpty) ...[
            _offerCarousel(addressId),
            _sectionHeading('Service Categories', onSeeAll: _openAllServices),
            _categoryStrip(addressId),
            _sectionHeading('Popular Services', onSeeAll: _openAllServices),
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
    final full = '${a['house_details'] ?? ''}, ${a['full_address'] ?? ''}'
        .replaceFirst(RegExp(r'^,\s*'), '')
        .trim();
    final hour = DateTime.now().hour;
    final greeting = hour < 12
        ? 'Morning'
        : hour < 17
        ? 'Afternoon'
        : 'Evening';
    return Container(
      color: _Ui.bg,
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.location_on_rounded,
                color: _Ui.violet,
                size: 22,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: InkWell(
                  onTap: _selectAddress,
                  borderRadius: BorderRadius.circular(8),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 5),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Text(
                              label,
                              style: const TextStyle(
                                color: _Ui.ink,
                                fontSize: 13,
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                            const Icon(
                              Icons.keyboard_arrow_down_rounded,
                              color: _Ui.ink,
                              size: 18,
                            ),
                          ],
                        ),
                        Text(
                          full.isEmpty ? 'Choose your service address' : full,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: _Ui.sub,
                            fontSize: 11.5,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              IconButton(
                tooltip: 'Your cart',
                onPressed: () => Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const CustomerCartScreen()),
                ),
                icon: const Icon(
                  Icons.shopping_bag_outlined,
                  color: _Ui.violet,
                  size: 24,
                ),
              ),
              IconButton(
                tooltip: 'Notifications',
                onPressed: _showNotificationsInfo,
                icon: const Icon(
                  Icons.notifications_none_rounded,
                  color: _Ui.ink,
                  size: 25,
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          Text(
            'Good $greeting, ${_customerName == 'there' ? 'there' : _customerName}!',
            style: const TextStyle(
              color: _Ui.ink,
              fontSize: 25,
              fontWeight: FontWeight.w900,
              height: 1.15,
            ),
          ),
          const SizedBox(height: 5),
          const Text(
            'What service do you need today?',
            style: TextStyle(color: _Ui.sub, fontSize: 13),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(child: _searchBar()),
              const SizedBox(width: 10),
              Material(
                color: _Ui.violet,
                borderRadius: BorderRadius.circular(16),
                child: InkWell(
                  borderRadius: BorderRadius.circular(16),
                  onTap: _openAllServices,
                  child: const SizedBox(
                    width: 52,
                    height: 52,
                    child: Icon(
                      Icons.tune_rounded,
                      color: Colors.white,
                      size: 23,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _sectionHeading(String title, {required VoidCallback onSeeAll}) =>
      Padding(
        padding: const EdgeInsets.fromLTRB(20, 22, 20, 12),
        child: Row(
          children: [
            Expanded(
              child: Text(
                title,
                style: const TextStyle(
                  color: _Ui.ink,
                  fontSize: 16,
                  fontWeight: FontWeight.w900,
                ),
              ),
            ),
            TextButton(
              onPressed: onSeeAll,
              style: TextButton.styleFrom(
                foregroundColor: _Ui.violet,
                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 4),
                minimumSize: Size.zero,
                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
              child: const Text(
                'See All',
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.w800),
              ),
            ),
          ],
        ),
      );

  IconData _categoryIcon(String name) {
    final value = name.toLowerCase();
    if (value.contains('clean')) return Icons.cleaning_services_rounded;
    if (value.contains('repair') || value.contains('electric')) {
      return Icons.handyman_rounded;
    }
    if (value.contains('plumb')) return Icons.plumbing_rounded;
    if (value.contains('paint')) return Icons.format_paint_rounded;
    if (value.contains('shift') || value.contains('move')) {
      return Icons.local_shipping_rounded;
    }
    if (value.contains('beauty') || value.contains('salon')) {
      return Icons.spa_rounded;
    }
    if (value.contains('car')) return Icons.directions_car_rounded;
    return Icons.grid_view_rounded;
  }

  String? _categoryImageForService(Service service) {
    for (final category in _catalogCategories) {
      if (category.id == service.categoryId && category.image != null) {
        return category.image;
      }
      for (final child in category.children) {
        if (child.id == service.categoryId && child.image != null) {
          return child.image;
        }
      }
    }
    return null;
  }

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
                    decoration: BoxDecoration(
                      color: _Ui.pale,
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: Icon(
                      _categoryIcon(category.title),
                      color: _Ui.violet,
                      size: 29,
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

  Widget _dynamicCategoryGrid(List<Category> categories, int? addressId) {
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
                      style: const TextStyle(color: _Ui.sub, fontSize: 11),
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

  Widget _walletReferralCard() => Padding(
    padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
    child: Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: _Ui.line),
        boxShadow: [
          BoxShadow(
            color: _Ui.violet.withAlpha(12),
            blurRadius: 16,
            offset: const Offset(0, 5),
          ),
        ],
      ),
      child: Column(
        children: [
          Row(
            children: [
              Container(
                width: 46,
                height: 46,
                decoration: BoxDecoration(
                  color: _Ui.pale,
                  borderRadius: BorderRadius.circular(15),
                ),
                child: const Icon(
                  Icons.account_balance_wallet_outlined,
                  color: _Ui.violet,
                  size: 25,
                ),
              ),
              const SizedBox(width: 12),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'AIRway Wallet',
                      style: TextStyle(
                        color: _Ui.ink,
                        fontSize: 15,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                    SizedBox(height: 3),
                    Text(
                      'Your balance and transactions',
                      style: TextStyle(color: _Ui.sub, fontSize: 11.5),
                    ),
                  ],
                ),
              ),
              TextButton(
                onPressed: () {
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (context) => const WalletScreen(),
                    ),
                  );
                },
                child: const Text('View'),
              ),
            ],
          ),
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 13),
            child: Divider(height: 1, color: _Ui.line),
          ),
          Row(
            children: [
              Container(
                width: 46,
                height: 46,
                decoration: BoxDecoration(
                  color: const Color(0xFFFFF0F8),
                  borderRadius: BorderRadius.circular(15),
                ),
                child: const Icon(
                  Icons.card_giftcard_rounded,
                  color: Color(0xFFD94691),
                  size: 25,
                ),
              ),
              const SizedBox(width: 12),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Invite friends & earn',
                      style: TextStyle(
                        color: _Ui.ink,
                        fontSize: 15,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                    SizedBox(height: 3),
                    Text(
                      'Referral rewards are being prepared',
                      style: TextStyle(color: _Ui.sub, fontSize: 11.5),
                    ),
                  ],
                ),
              ),
              OutlinedButton(
                onPressed: _showReferralInfo,
                style: OutlinedButton.styleFrom(
                  foregroundColor: _Ui.violet,
                  side: const BorderSide(color: _Ui.violet),
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(13),
                  ),
                ),
                child: const Text('Invite'),
              ),
            ],
          ),
        ],
      ),
    ),
  );

  Widget _nearbyWorkersSection() => Padding(
    padding: const EdgeInsets.only(top: 4),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _heading(
          'Available Partners Near You',
          'Verified workers currently online in your service zone',
        ),
        if (_workersLoading)
          const Padding(
            padding: EdgeInsets.fromLTRB(20, 4, 20, 8),
            child: LinearProgressIndicator(minHeight: 3),
          )
        else if (_workersError != null)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: Row(
              children: [
                const Expanded(
                  child: Text(
                    'Partner availability could not be loaded.',
                    style: TextStyle(color: _Ui.sub, fontSize: 12),
                  ),
                ),
                TextButton(
                  onPressed: () {
                    final id = _active?['id'];
                    if (id != null) _loadNearbyWorkers(id.toString());
                  },
                  child: const Text('Retry'),
                ),
              ],
            ),
          )
        else if (_nearbyWorkers.isEmpty)
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 4),
            child: Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(18),
                border: Border.all(color: _Ui.line),
              ),
              child: Row(
                children: [
                  const Icon(
                    Icons.support_agent_rounded,
                    color: _Ui.violet,
                    size: 30,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      _workersMessage ?? 'No verified partners are online in this service zone right now. Availability updates when approved workers go online.',
                      style: const TextStyle(
                        color: _Ui.sub,
                        fontSize: 12,
                        height: 1.4,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          )
        else
          SizedBox(
            height: 150,
            child: ListView.separated(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              scrollDirection: Axis.horizontal,
              itemCount: _nearbyWorkers.length,
              separatorBuilder: (_, __) => const SizedBox(width: 12),
              itemBuilder: (context, index) {
                final worker = _nearbyWorkers[index];
                final services = worker['services'] is List
                    ? (worker['services'] as List)
                          .map((e) => e.toString())
                          .join(' · ')
                    : 'Home services';
                final rating = double.tryParse('${worker['rating'] ?? ''}');
                return Container(
                  width: 215,
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(color: _Ui.line),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          CircleAvatar(
                            backgroundColor: _Ui.pale,
                            child: const Icon(
                              Icons.person_rounded,
                              color: _Ui.violet,
                            ),
                          ),
                          const SizedBox(width: 9),
                          Expanded(
                            child: Text(
                              '${worker['name'] ?? 'Verified partner'}',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                color: _Ui.ink,
                                fontWeight: FontWeight.w800,
                                fontSize: 13,
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 10),
                      Row(
                        children: [
                          Container(
                            width: 7,
                            height: 7,
                            decoration: const BoxDecoration(
                              color: Color(0xFF20B779),
                              shape: BoxShape.circle,
                            ),
                          ),
                          const SizedBox(width: 5),
                          const Text(
                            'Online',
                            style: TextStyle(
                              color: Color(0xFF159A64),
                              fontSize: 11,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                          if (rating != null && rating > 0) ...[
                            const Spacer(),
                            const Icon(
                              Icons.star_rounded,
                              size: 15,
                              color: Color(0xFFFFB020),
                            ),
                            Text(
                              rating.toStringAsFixed(1),
                              style: const TextStyle(
                                color: _Ui.ink,
                                fontSize: 11,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ],
                        ],
                      ),
                      const Spacer(),
                      Text(
                        services,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: _Ui.sub,
                          fontSize: 11.5,
                          height: 1.25,
                        ),
                      ),
                    ],
                  ),
                );
              },
            ),
          ),
      ],
    ),
  );

  Widget _searchBar() => TextField(
    controller: _search,
    focusNode: _searchFocus,
    textInputAction: TextInputAction.search,
    onChanged: (v) => setState(() => _query = v),
    decoration: InputDecoration(
      hintText: 'Search services…',
      hintStyle: const TextStyle(fontSize: 12.5, color: _Ui.sub),
      prefixIcon: const Icon(Icons.search_rounded, color: _Ui.sub),
      suffixIcon: _query.isEmpty
          ? IconButton(
              tooltip: 'Search by voice',
              onPressed: _startVoiceSearch,
              icon: const Icon(Icons.mic_none_rounded, color: _Ui.sub),
            )
          : IconButton(
              tooltip: 'Clear search',
              onPressed: () {
                _search.clear();
                _searchFocus.unfocus();
                setState(() => _query = '');
              },
              icon: const Icon(Icons.close_rounded, size: 19, color: _Ui.sub),
            ),
      filled: true,
      fillColor: Colors.white,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: BorderSide.none,
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: BorderSide(color: _Ui.line),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(color: _Ui.violet, width: 1.3),
      ),
      contentPadding: const EdgeInsets.symmetric(vertical: 15),
    ),
  );

  Widget _heading(String title, String subtitle) => Padding(
    padding: const EdgeInsets.fromLTRB(20, 26, 20, 13),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: const TextStyle(
            fontSize: 21,
            fontWeight: FontWeight.w900,
            color: _Ui.ink,
          ),
        ),
        const SizedBox(height: 3),
        Text(subtitle, style: const TextStyle(fontSize: 12.5, color: _Ui.sub)),
      ],
    ),
  );

  Widget _trustStrip() => Padding(
    padding: const EdgeInsets.fromLTRB(20, 20, 20, 0),
    child: Container(
      decoration: BoxDecoration(
        color: _Ui.pale,
        borderRadius: BorderRadius.circular(20),
      ),
      padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 5),
      child: Row(
        children: [
          _trustItem(Icons.location_on_outlined, 'Local focus'),
          _trustItem(Icons.receipt_long_outlined, 'Clear pricing'),
          _trustItem(Icons.support_agent_outlined, 'Support'),
        ],
      ),
    ),
  );

  Widget _trustItem(IconData icon, String title) => Expanded(
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, color: _Ui.violet, size: 25),
        const SizedBox(height: 6),
        Text(
          title,
          textAlign: TextAlign.center,
          maxLines: 2,
          style: const TextStyle(
            fontSize: 11,
            fontWeight: FontWeight.w700,
            color: _Ui.ink,
          ),
        ),
      ],
    ),
  );

  String _photoForService(Service service) {
    final name = '${service.title} ${service.categoryName}'.toLowerCase();
    if (name.contains('sofa') || name.contains('upholstery')) {
      return 'https://images.unsplash.com/photo-1555041469-a586c61ea9bc?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('garden') || name.contains('plant') || name.contains('lawn')) {
      return 'https://images.unsplash.com/photo-1416879595882-3373a0480b5b?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('kitchen')) {
      return 'https://images.unsplash.com/photo-1600489000022-c2086d79f9d4?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('bathroom')) {
      return 'https://images.unsplash.com/photo-1620626011761-996317b8d101?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('bedroom') || name.contains('living room') || name.contains('home cleaning') || name.contains('cleaning')) {
      return 'https://images.unsplash.com/photo-1581578731548-c64695cc6952?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('car') || name.contains('vehicle') || name.contains('wash')) {
      return 'https://images.unsplash.com/photo-1607860108855-64acf2078ed9?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('beauty') || name.contains('salon') || name.contains('hair')) {
      return 'https://images.unsplash.com/photo-1560066984-138dadb4c035?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('electric') || name.contains('wiring')) {
      return 'https://images.unsplash.com/photo-1621905251189-08b45d6a269e?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('plumb')) {
      return 'https://images.unsplash.com/photo-1607472586893-edb57bdc0e39?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('paint')) {
      return 'https://images.unsplash.com/photo-1562259949-e8e7689d7828?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('repair') || name.contains('handyman')) {
      return 'https://images.unsplash.com/photo-1581244277943-fe4a9c777189?auto=format&fit=crop&w=900&q=85';
    }
    return 'https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?auto=format&fit=crop&w=900&q=85';
  }

  String _photoForBanner(String title, int index) {
    final value = title.toLowerCase();
    if (value.contains('repair') || value.contains('electric')) {
      return 'https://images.unsplash.com/photo-1621905251189-08b45d6a269e?auto=format&fit=crop&w=1400&q=88';
    }
    if (value.contains('garden') || value.contains('plant')) {
      return 'https://images.unsplash.com/photo-1416879595882-3373a0480b5b?auto=format&fit=crop&w=1400&q=88';
    }
    if (value.contains('sofa') || value.contains('furniture')) {
      return 'https://images.unsplash.com/photo-1555041469-a586c61ea9bc?auto=format&fit=crop&w=1400&q=88';
    }
    if (value.contains('beauty') || value.contains('salon')) {
      return 'https://images.unsplash.com/photo-1560066984-138dadb4c035?auto=format&fit=crop&w=1400&q=88';
    }
    if (value.contains('car')) {
      return 'https://images.unsplash.com/photo-1607860108855-64acf2078ed9?auto=format&fit=crop&w=1400&q=88';
    }
    if (value.contains('clean') || value.contains('home')) {
      return 'https://images.unsplash.com/photo-1581578731548-c64695cc6952?auto=format&fit=crop&w=1400&q=88';
    }
    const defaults = [
      'https://images.unsplash.com/photo-1581578731548-c64695cc6952?auto=format&fit=crop&w=1400&q=88',
      'https://images.unsplash.com/photo-1621905251189-08b45d6a269e?auto=format&fit=crop&w=1400&q=88',
      'https://images.unsplash.com/photo-1416879595882-3373a0480b5b?auto=format&fit=crop&w=1400&q=88',
    ];
    return defaults[index % defaults.length];
  }

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
                      child: Builder(
                        builder: (context) {
                          final imageUrl = service.image?.isNotEmpty == true
                              ? service.image
                              : service.images.isNotEmpty
                                  ? service.images.first.image
                                  : _photoForService(service);
                          if (imageUrl == null || imageUrl.isEmpty) {
                            return Container(
                              color: _Ui.pale,
                              child: const Icon(
                                Icons.home_repair_service_rounded,
                                color: _Ui.violet,
                                size: 42,
                              ),
                            );
                          }
                          return Image.network(
                            imageUrl,
                            fit: BoxFit.cover,
                            errorBuilder: (_, __, ___) => Container(
                              color: _Ui.pale,
                              child: const Icon(
                                Icons.home_repair_service_rounded,
                                color: _Ui.violet,
                                size: 42,
                              ),
                            ),
                          );
                        },
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

  Widget _offerCarousel(int? addressId) {
    // Keep the hero directly below search visible even before admin banners
    // are uploaded. Every fallback image is a real service-related photograph.
    final adminBanners = _homeBanners;
    final fallbackTitles = [
      'Clean Spaces, Happier Days',
      'Repairs Made Simple',
      'Professional Care at Your Doorstep',
    ];
    final count = adminBanners.isNotEmpty ? adminBanners.length : fallbackTitles.length;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: SizedBox(
        height: 174,
        child: PageView.builder(
          itemCount: count,
          controller: _bannerController,
          itemBuilder: (context, index) {
            final banner = adminBanners.isNotEmpty ? adminBanners[index] : null;
            final title = banner?.title.trim().isNotEmpty == true
                ? banner!.title
                : fallbackTitles[index % fallbackTitles.length];
            final imageUrl = banner?.image?.isNotEmpty == true
                ? banner!.image!
                : _photoForBanner(title, index);

            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 2),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(18),
                child: Material(
                  color: const Color(0xFFE7F2EC),
                  child: InkWell(
                    onTap: () {
                      final serviceId = banner?.linkServiceId;
                      if (serviceId != null) {
                        final service = _popularCatalogServices
                            .where((item) => item.id == serviceId)
                            .firstOrNull;
                        if (service != null) {
                          _openCatalogService(service, addressId);
                          return;
                        }
                      }
                      _openAllServices();
                    },
                    child: Stack(
                      fit: StackFit.expand,
                      children: [
                        Image.network(
                          imageUrl,
                          fit: BoxFit.cover,
                          errorBuilder: (_, __, ___) => Image.network(
                            _photoForBanner(title, index),
                            fit: BoxFit.cover,
                            errorBuilder: (_, __, ___) =>
                                const ColoredBox(color: Color(0xFF245C45)),
                          ),
                        ),
                        const DecoratedBox(
                          decoration: BoxDecoration(
                            gradient: LinearGradient(
                              begin: Alignment.centerLeft,
                              end: Alignment.centerRight,
                              colors: [
                                Color(0xE6000000),
                                Color(0x88000000),
                                Colors.transparent,
                              ],
                              stops: [0, 0.58, 1],
                            ),
                          ),
                        ),
                        Padding(
                          padding: const EdgeInsets.fromLTRB(20, 18, 18, 16),
                          child: Align(
                            alignment: Alignment.centerLeft,
                            child: SizedBox(
                              width: 225,
                              child: Column(
                                mainAxisAlignment: MainAxisAlignment.center,
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    title,
                                    maxLines: 2,
                                    overflow: TextOverflow.ellipsis,
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 21,
                                      height: 1.12,
                                      fontWeight: FontWeight.w900,
                                    ),
                                  ),
                                  const SizedBox(height: 12),
                                  Container(
                                    padding: const EdgeInsets.symmetric(
                                      horizontal: 14,
                                      vertical: 8,
                                    ),
                                    decoration: BoxDecoration(
                                      color: Colors.white,
                                      borderRadius: BorderRadius.circular(10),
                                    ),
                                    child: const Text(
                                      'Book Now',
                                      style: TextStyle(
                                        color: _Ui.violet,
                                        fontSize: 11.5,
                                        fontWeight: FontWeight.w800,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _bookings() => const BookingListScreen();

  Widget _profile(Map<String, dynamic> address) => ListView(
    padding: const EdgeInsets.all(20),
    children: [
      const Text(
        'Profile',
        style: TextStyle(
          fontSize: 26,
          fontWeight: FontWeight.w900,
          color: _Ui.ink,
        ),
      ),
      const SizedBox(height: 16),
      Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: _Ui.pale,
          borderRadius: BorderRadius.circular(22),
        ),
        child: Row(
          children: [
            const CircleAvatar(
              radius: 24,
              backgroundColor: Colors.white,
              child: Icon(Icons.person_outline, color: _Ui.violet),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Your AIRway account',
                    style: TextStyle(
                      fontSize: 17,
                      fontWeight: FontWeight.w800,
                      color: _Ui.ink,
                    ),
                  ),
                  Text(
                    '${_addresses.length} saved addresses',
                    style: const TextStyle(color: _Ui.sub),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
      const SizedBox(height: 16),

      // Worker application status
      if (_workerProfile != null) ...[
        _buildWorkerStatusCard(),
        const SizedBox(height: 16),
      ],

      // Show registration only when no application exists
      if (_workerStatus == null || _workerStatus == 'no_profile') ...[
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

      Card(
        color: Colors.white,
        elevation: 0,
        child: Column(
          children: [
            ListTile(
              leading: const Icon(
                Icons.location_on_outlined,
                color: _Ui.violet,
              ),
              title: const Text('Manage addresses'),
              subtitle: Text(
                '${address['full_address'] ?? ''}',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              trailing: const Icon(Icons.chevron_right),
              onTap: _selectAddress,
            ),
            const Divider(height: 1, indent: 16, endIndent: 16),
            ListTile(
              leading: const Icon(
                Icons.account_balance_wallet_outlined,
                color: _Ui.violet,
              ),
              title: const Text('Wallet'),
              subtitle: const Text('View balance and transactions'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () {
                Navigator.of(context).push(
                  MaterialPageRoute(builder: (context) => const WalletScreen()),
                );
              },
            ),
            const Divider(height: 1, indent: 16, endIndent: 16),
            ListTile(
              leading: const Icon(Icons.refresh, color: _Ui.violet),
              title: const Text('Refresh account data'),
              onTap: _refresh,
            ),
            const Divider(height: 1, indent: 16, endIndent: 16),
            ListTile(
              leading: const Icon(Icons.rate_review_rounded, color: _Ui.violet),
              title: const Text('My Ratings'),
              subtitle: const Text('Rate your service providers'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () {
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (context) => const RatingsScreen(),
                  ),
                );
              },
            ),
            const Divider(height: 1, indent: 16, endIndent: 16),
            ListTile(
              leading: const Icon(Icons.logout_rounded, color: _Ui.violet),
              title: const Text('Log out'),
              onTap: _logout,
            ),
          ],
        ),
      ),
    ],
  );

  Widget _buildWorkerHomeStatusCard() {
    final status = _workerStatus;
    final isPending = status == 'pending';
    final isApproved = status == 'approved';
    final isRejected = status == 'rejected';

    final color = isPending
        ? const Color(0xFFFFF4DF)
        : isApproved
        ? const Color(0xFFE7F2EC)
        : const Color(0xFFFDECEC);

    final accent = isPending
        ? const Color(0xFFB7791F)
        : isApproved
        ? _Ui.violet
        : const Color(0xFFB42318);

    final title = isPending
        ? 'Worker application pending'
        : isApproved
        ? 'You are an approved AIRway worker'
        : 'Worker application needs attention';

    final message = isPending
        ? 'Your application is with our admin team for review. We’ll update this status when a decision is made.'
        : isApproved
        ? 'Your application is approved. Continue to your Worker Dashboard to start managing jobs.'
        : (_workerRejectionReason?.isNotEmpty == true
              ? 'Reason: $_workerRejectionReason'
              : 'Your application was not approved. Open your application to review the next step.');

    return Material(
      color: color,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        // Pending is informational only; never send a submitted application back to the form.
        onTap: isApproved || isPending ? null : _viewWorkerStatus,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(
                isPending
                    ? Icons.pending_actions_rounded
                    : isApproved
                    ? Icons.verified_rounded
                    : Icons.error_outline_rounded,
                color: accent,
                size: 25,
              ),
              const SizedBox(width: 11),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: TextStyle(
                        color: accent,
                        fontSize: 13,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      message,
                      style: const TextStyle(
                        color: _Ui.ink,
                        fontSize: 11.5,
                        height: 1.4,
                      ),
                    ),
                    if (isApproved) ...[
                      const SizedBox(height: 12),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: FilledButton.icon(
                          onPressed: _switchToWorkerMode,
                          icon: const Icon(Icons.arrow_forward_rounded, size: 17),
                          label: const Text('Continue as Worker'),
                          style: FilledButton.styleFrom(
                            backgroundColor: _Ui.violet,
                            foregroundColor: Colors.white,
                            padding: const EdgeInsets.symmetric(
                              horizontal: 14,
                              vertical: 10,
                            ),
                            textStyle: const TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w800,
                            ),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(10),
                            ),
                          ),
                        ),
                      ),
                    ],
                    if (isRejected) ...[
                      const SizedBox(height: 7),
                      Text(
                        'View application  ›',
                        style: TextStyle(
                          color: accent,
                          fontSize: 11,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

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
            ? Text(
                _workerRejectionReason?.isNotEmpty == true
                    ? 'Reason: $_workerRejectionReason'
                    : 'Your application was not approved',
              )
            : const Text('Register to earn by providing services'),
        trailing: isApproved
            ? Switch(value: true, onChanged: (_) => _switchToWorkerMode())
            : isPending
            ? null
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

class _PulseBlockState extends State<_PulseBlock>
    with SingleTickerProviderStateMixin {
  late final AnimationController _animation = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1100),
  )..repeat(reverse: true);

  @override
  void dispose() {
    _animation.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _animation,
      builder: (context, _) => Container(
        height: widget.height,
        decoration: BoxDecoration(
          color: Color.lerp(
            const Color(0xFFE9E5F3),
            const Color(0xFFF6F3FA),
            _animation.value,
          ),
          borderRadius: BorderRadius.circular(21),
        ),
      ),
    );
  }
}
