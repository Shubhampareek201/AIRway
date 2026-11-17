import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:latlong2/latlong.dart' as ll;
import 'package:airway/core/storage/secure_session_storage.dart';
import 'package:airway/features/location/data/location_api.dart';
import 'package:airway/features/location/presentation/address_picker_screen.dart';
import 'package:airway/features/location/presentation/location_selection_screen.dart';
import 'package:airway/features/welcome/presentation/welcome_screen.dart';
import 'package:airway/features/booking/presentation/booking_list_screen.dart';
import 'package:airway/features/booking/presentation/customer_order_screen.dart';
import 'package:airway/features/notification/data/push_notification_service.dart';
import 'package:airway/features/booking/presentation/customer_cart_screen.dart';
import 'package:airway/features/notification/presentation/notification_bell_button.dart';
import 'package:airway/features/ratings/presentation/ratings_screen.dart';
import 'package:airway/features/account/presentation/account_profile_screen.dart';
import 'package:airway/features/account/presentation/notification_preferences_screen.dart';
import 'package:airway/features/account/presentation/account_preferences_screen.dart';
import 'package:airway/core/localization/airway_locale.dart';
import 'package:airway/features/account/presentation/account_referrals_screen.dart';
import 'package:airway/features/account/presentation/account_deletion_screen.dart';
import 'package:airway/features/account/presentation/legal_documents_screen.dart';
import 'package:airway/features/account/presentation/account_security_screen.dart';
import 'package:airway/features/account/presentation/payment_options_screen.dart';
import 'package:airway/features/account/presentation/help_support_screen.dart';
import 'package:airway/features/favorites/presentation/favorite_services_screen.dart';
import 'package:airway/features/wallet/presentation/wallet_screen.dart';
import 'package:airway/features/worker/presentation/worker_application_screen.dart';
import 'package:airway/features/worker/presentation/worker_dashboard_screen.dart';
import 'package:airway/features/worker/data/worker_app_api.dart';
import 'package:airway/features/catalog/data/catalog_api.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';
import 'package:airway/features/catalog/data/catalog_image_resolver.dart';
import 'package:airway/features/catalog/presentation/service_categories_screen.dart';
import 'package:airway/features/catalog/presentation/car_wash_vehicle_screen.dart';
import 'package:airway/features/catalog/presentation/category_decision_screen.dart';
import 'package:airway/features/catalog/presentation/beauty_audience_screen.dart';
import 'package:airway/features/catalog/data/catalog_category_image_resolver.dart';
import 'package:airway/features/catalog/data/beauty_audience.dart';
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
  StreamSubscription<RemoteMessage>? _pushOpenSubscription;
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
  Map<String, dynamic>? _accountData;
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
    PushNotificationService.initializeForAuthenticatedUser().catchError((_) {});
    _pushOpenSubscription = FirebaseMessaging.onMessageOpenedApp.listen(_handlePushOpen);
    FirebaseMessaging.instance.getInitialMessage().then((message) {
      if (message != null) _handlePushOpen(message);
    });
    _refresh();
  }

  void _handlePushOpen(RemoteMessage message) {
    if (!mounted || message.data['notification_kind'] != 'customer_completion_otp') return;
    final orderId = int.tryParse(message.data['order_id']?.toString() ?? '');
    if (orderId == null) return;
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => CustomerOrderScreen(orderId: orderId),
    ));
  }

  @override
  void dispose() {
    _pushOpenSubscription?.cancel();
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

  Category? _findCatalogCategoryById(List<Category> categories, int id) {
    for (final item in categories) {
      if (item.id == id) return item;
      final nested = _findCatalogCategoryById(item.children, id);
      if (nested != null) return nested;
    }
    return null;
  }

  Future<void> _openCatalogCategory(Category category, int? addressId) async {
    _searchFocus.unfocus();
    var answers = <String, dynamic>{};
    if (category.slug == 'beauty') {
      final audience = await BeautyAudienceScreen.choose(context);
      if (audience == null || !mounted) return;
      answers['beauty_audience'] = audience;
    }
    final categoryIdentity =
        '${category.slug} ${category.title}'.toLowerCase().replaceAll(
          RegExp(r'[^a-z0-9]+'),
          ' ',
        ).trim();
    final isCarWash = categoryIdentity.contains('car wash') ||
        categoryIdentity.replaceAll(' ', '').contains('carwash');

    if (isCarWash) {
      Navigator.of(context).push<void>(
        MaterialPageRoute(
          builder: (_) => CarWashVehicleScreen(
            vehicleTypeSteps: {
              for (final child in category.children)
                if (child.slug == 'car' || child.slug == 'bike')
                  child.slug: child.customerFlowSteps,
            },
            onContinue: (vehicleContext, selectedAnswers) async {
              final selectedAnswersCopy = Map<String, dynamic>.from(selectedAnswers);
              final vehicleSlug =
                  selectedAnswersCopy['vehicle_kind']?.toString().toLowerCase() == 'bike'
                      ? 'bike'
                      : 'car';
              final selectedVehicleCategory = category.children
                  .where((child) => child.slug.toLowerCase() == vehicleSlug)
                  .firstOrNull;
              if (selectedVehicleCategory == null) {
                ScaffoldMessenger.of(vehicleContext).showSnackBar(
                  SnackBar(content: Text('The $vehicleSlug service category is not configured yet.')),
                );
                return;
              }

              try {
                final filteredRoots = await CatalogApi.listCategories(
                  addressId: addressId,
                  categoryAnswers: selectedAnswersCopy,
                );
                Category? findCategory(List<Category> items, int id) {
                  for (final item in items) {
                    if (item.id == id) return item;
                    final nested = findCategory(item.children, id);
                    if (nested != null) return nested;
                  }
                  return null;
                }

                final filteredVehicleCategory =
                    findCategory(filteredRoots, selectedVehicleCategory.id) ??
                    selectedVehicleCategory;
                final categoriesToShow = filteredVehicleCategory.children;
                if (categoriesToShow.isEmpty) {
                  ScaffoldMessenger.of(vehicleContext).showSnackBar(
                    SnackBar(content: Text('No service categories are configured for $vehicleSlug yet.')),
                  );
                  return;
                }

                if (!vehicleContext.mounted) return;
                Navigator.of(vehicleContext).pushReplacement<void, void>(
                  MaterialPageRoute(
                    builder: (_) => ServiceCategoriesScreen(
                      initialCategories: categoriesToShow,
                      addressId: addressId,
                      title: filteredVehicleCategory.title,
                      initialAnswers: selectedAnswersCopy,
                    ),
                  ),
                );
              } catch (e) {
                if (!vehicleContext.mounted) return;
                ScaffoldMessenger.of(vehicleContext).showSnackBar(
                  SnackBar(content: Text('Could not load matching vehicle categories: $e')),
                );
              }
            },
          ),
        ),
      );
      return;
    }

    if (category.customerFlowSteps.isNotEmpty) {
      // Keep personalisation visible while resolving the selected branch.
      // Replace this route only when the destination is ready.
      Navigator.of(context).push<void>(
        MaterialPageRoute(
          builder: (_) => CategoryDecisionScreen(
            categoryTitle: category.title,
            steps: category.customerFlowSteps,
            onContinue: (flowContext, selected) async {
              final routeAnswers = Map<String, dynamic>.from(selected);
              final nextCategorySlug =
                  routeAnswers.remove('__next_category_slug')?.toString().trim();
              final nextCategoryId = int.tryParse(
                routeAnswers.remove('__next_category_id')?.toString() ?? '',
              );

              Category routedCategory = category;
              try {
                if (nextCategoryId != null ||
                    (nextCategorySlug != null && nextCategorySlug.isNotEmpty)) {
                  final targets = category.children.where((child) {
                    if (nextCategoryId != null) return child.id == nextCategoryId;
                    return child.slug.toLowerCase() == nextCategorySlug!.toLowerCase();
                  }).toList();
                  if (targets.length != 1) {
                    ScaffoldMessenger.of(flowContext).showSnackBar(
                      const SnackBar(
                        content: Text(
                          'The next category is not configured correctly. Please contact support.',
                        ),
                      ),
                    );
                    return;
                  }
                  routedCategory = targets.first;
                }

                final freshRoots = await CatalogApi.listCategories(
                  addressId: addressId,
                  audience: routeAnswers['beauty_audience']?.toString(),
                );
                if (nextCategoryId != null ||
                    (nextCategorySlug != null && nextCategorySlug.isNotEmpty)) {
                  routedCategory =
                      _findCatalogCategoryById(freshRoots, routedCategory.id) ??
                          routedCategory;
                }

                if (!flowContext.mounted) return;
                final Widget destination = routedCategory.children.isNotEmpty
                    ? ServiceCategoriesScreen(
                        initialCategories: routedCategory.children,
                        addressId: addressId,
                        title: routedCategory.title,
                        initialAnswers: routeAnswers,
                      )
                    : ServiceListScreen(
                        categoryId: routedCategory.id,
                        categoryTitle: routedCategory.title,
                        addressId: addressId,
                        initialAnswers: routeAnswers,
                      );

                Navigator.of(flowContext).pushReplacement<void, void>(
                  MaterialPageRoute(builder: (_) => destination),
                );
              } catch (e) {
                if (!flowContext.mounted) return;
                ScaffoldMessenger.of(flowContext).showSnackBar(
                  SnackBar(
                    content: Text(
                      'Could not load the selected service category. Please try again. ($e)',
                    ),
                  ),
                );
              }
            },
          ),
        ),
      );
      return;
    }

    if (!mounted) return;
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

  Category? _rootCategoryForService(int categoryId) {
    bool containsCategory(Category category) {
      if (category.id == categoryId) return true;
      return category.children.any(containsCategory);
    }
    for (final root in _catalogCategories) {
      if (containsCategory(root)) return root;
    }
    return null;
  }

  Future<void> _openCatalogService(Service service, int? addressId) async {
    _searchFocus.unfocus();
    var answers = <String, dynamic>{};
    final root = _rootCategoryForService(service.categoryId);
    if (root?.slug == 'beauty') {
      final audience = await BeautyAudienceScreen.choose(context);
      if (audience == null || !mounted) return;
      if (!BeautyAudience.includes(
        selected: audience,
        serviceAudience: service.audience,
      )) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              service.audience == 'men'
                  ? 'This service is listed under Men. Choose Men to continue.'
                  : 'This service is listed under Women. Choose Women to continue.',
            ),
          ),
        );
        return;
      }
      answers['beauty_audience'] = audience;
    } else if (root != null && root.customerFlowSteps.isNotEmpty) {
      final selected = await Navigator.push<Map<String, dynamic>>(
        context,
        MaterialPageRoute(
          builder: (_) => CategoryDecisionScreen(
            categoryTitle: root.title,
            steps: root.customerFlowSteps,
          ),
        ),
      );
      if (selected == null || !mounted) return;
      answers = selected;
    }
    if (!mounted) return;
    Navigator.push<void>(
      context,
      MaterialPageRoute(
        builder: (_) => catalog.ServiceDetailScreen(
          serviceId: service.id,
          addressId: addressId,
          initialAnswers: answers,
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
      if (mounted) setState(() => _accountData = data);
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

  Future<void> _editAccountProfile() async {
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => const AccountProfileScreen()),
    );
    if (changed == true && mounted) await _loadCustomerName();
  }

  Future<void> _openNotificationPreferences() async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute(builder: (_) => const NotificationPreferencesScreen()),
    );
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
    try {
      await PushNotificationService.unregisterCurrentDevice();
    } catch (_) {
      // Continue logout even if the push service is temporarily unavailable.
    }
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
          const Padding(
            padding: EdgeInsets.only(bottom: 12),
            child: Align(
              alignment: Alignment.centerLeft,
              child: _AnimatedAirwayBrand(),
            ),
          ),
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
              const NotificationBellButton(color: _Ui.ink),
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

  String? _photoForCategory(Category category) =>
      CatalogCategoryImageResolver.forCategory(
        slug: category.slug,
        title: category.title,
      );

  Widget _categoryPhotoWidget(Category category, {double? size}) {
    final url = category.image?.isNotEmpty == true
        ? category.image
        : _photoForCategory(category);
    final placeholder = Container(
      width: size,
      height: size,
      color: _Ui.pale,
      alignment: Alignment.center,
      child: Icon(_categoryIcon(category.title), color: _Ui.violet, size: 30),
    );
    if (url == null) return placeholder;
    return Image.network(
      url,
      width: size,
      height: size,
      fit: BoxFit.cover,
      errorBuilder: (_, __, ___) => placeholder,
    );
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
                    clipBehavior: Clip.antiAlias,
                    child: _categoryPhotoWidget(category, size: 58),
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
                      child: _categoryPhotoWidget(category),
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

  String? _photoForService(Service service) =>
      CatalogImageResolver.forService(
        title: service.title,
        categoryName: service.categoryName,
        audience: service.audience,
      );

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

  Widget _profile(Map<String, dynamic> address) {
    final hi = AirwayLocale.current.languageCode == 'hi';
    final account = _accountData ?? const <String, dynamic>{};
    final name = account['name']?.toString().trim();
    final email = account['email']?.toString().trim();
    final phone = account['phone']?.toString().trim();
    final photoUrl = account['photo_url']?.toString();
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        const Text(
          hi ? 'प्रोफ़ाइल' : 'Profile',
          style: TextStyle(fontSize: 26, fontWeight: FontWeight.w900, color: _Ui.ink),
        ),
        const SizedBox(height: 16),
        Container(
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(color: _Ui.pale, borderRadius: BorderRadius.circular(22)),
          child: Row(
            children: [
              CircleAvatar(
                radius: 30,
                backgroundColor: Colors.white,
                backgroundImage: photoUrl != null && photoUrl.isNotEmpty ? NetworkImage(photoUrl) : null,
                child: photoUrl == null || photoUrl.isEmpty
                    ? const Icon(Icons.person_outline, color: _Ui.violet, size: 30)
                    : null,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(name?.isNotEmpty == true ? name! : hi ? 'आपका AIRway खाता' : 'Your AIRway account',
                        style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800, color: _Ui.ink)),
                    if (phone?.isNotEmpty == true)
                      Text(phone!, style: const TextStyle(color: _Ui.sub)),
                    if (email?.isNotEmpty == true)
                      Text(email!, maxLines: 1, overflow: TextOverflow.ellipsis,
                          style: const TextStyle(color: _Ui.sub, fontSize: 12)),
                    Text(hi ? '${_addresses.length} सहेजे गए पते' : '${_addresses.length} saved addresses', style: const TextStyle(color: _Ui.sub, fontSize: 12)),
                  ],
                ),
              ),
              IconButton(
                tooltip: hi ? 'व्यक्तिगत जानकारी संपादित करें' : 'Edit personal information',
                onPressed: _editAccountProfile,
                icon: const Icon(Icons.edit_outlined, color: _Ui.violet),
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        if (_workerProfile != null) ...[
          _buildWorkerStatusCard(),
          const SizedBox(height: 16),
        ],
        if (_workerStatus == null || _workerStatus == 'no_profile') ...[
          Card(
            color: Colors.white,
            elevation: 0,
            child: ListTile(
              leading: const Icon(Icons.work_outline, color: _Ui.violet),
              title: Text(hi ? 'वर्कर बनें' : 'Become a Worker'),
              subtitle: Text(hi ? 'अपने क्षेत्र में सेवाएँ देने के लिए आवेदन करें' : 'Apply to provide services in your area'),
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
                leading: const Icon(Icons.person_outline_rounded, color: _Ui.violet),
                title: Text(hi ? 'व्यक्तिगत जानकारी' : 'Personal information'),
                subtitle: Text(hi ? 'नाम, ईमेल, प्रोफ़ाइल फोटो और फ़ोन' : 'Name, email, profile photo and phone'),
                trailing: const Icon(Icons.chevron_right),
                onTap: _editAccountProfile,
              ),
              const Divider(height: 1, indent: 16, endIndent: 16),
              ListTile(
                leading: const Icon(Icons.location_on_outlined, color: _Ui.violet),
                title: Text(hi ? 'पते प्रबंधित करें' : 'Manage addresses'),
                subtitle: Text('${address['full_address'] ?? ''}', maxLines: 1, overflow: TextOverflow.ellipsis),
                trailing: const Icon(Icons.chevron_right),
                onTap: _selectAddress,
              ),
              const Divider(height: 1, indent: 16, endIndent: 16),
              ListTile(
                leading: const Icon(Icons.calendar_month_outlined, color: _Ui.violet),
                title: Text(hi ? 'मेरी बुकिंग' : 'My Bookings'),
                subtitle: Text(hi ? 'आगामी, चालू और पूरी हुई सेवाएँ' : 'Upcoming, active and completed services'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => setState(() => _tab = 1),
              ),
              const Divider(height: 1, indent: 16, endIndent: 16),
              ListTile(
                leading: const Icon(Icons.favorite_border_rounded, color: _Ui.violet),
                title: Text(hi ? 'पसंदीदा सेवाएँ' : 'Favorite services'),
                subtitle: Text(hi ? 'बाद के लिए सेव की गई सेवाएँ' : 'Services you saved for later'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => FavoriteServicesScreen(addressId: int.tryParse('${address['id']}'))),
                ),
              ),
              const Divider(height: 1, indent: 16, endIndent: 16),
              ListTile(
                leading: const Icon(Icons.account_balance_wallet_outlined, color: _Ui.violet),
                title: Text(hi ? 'वॉलेट' : 'Wallet'),
                subtitle: Text(hi ? 'बैलेंस और लेन-देन देखें' : 'View balance and transactions'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const WalletScreen()),
                ),
              ),
              const Divider(height: 1, indent: 16, endIndent: 16),
              ListTile(
                leading: const Icon(Icons.rate_review_rounded, color: _Ui.violet),
                title: Text(hi ? 'मेरी रेटिंग' : 'My Ratings'),
                subtitle: Text(hi ? 'आपकी सेवा प्रतिक्रिया और रेटिंग' : 'Your service feedback and ratings'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const RatingsScreen()),
                ),
              ),
              const Divider(height: 1, indent: 16, endIndent: 16),
              ListTile(
                leading: const Icon(Icons.payments_outlined, color: _Ui.violet),
                title: Text(hi ? 'भुगतान विकल्प' : 'Payment options'),
                subtitle: Text(hi ? 'वॉलेट और सुरक्षित ऑनलाइन भुगतान के तरीके' : 'Wallet and secure online checkout methods'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const PaymentOptionsScreen()),
                ),
              ),
              const Divider(height: 1, indent: 16, endIndent: 16),
              ListTile(
                leading: const Icon(Icons.notifications_outlined, color: _Ui.violet),
                title: Text(hi ? 'सूचना प्राथमिकताएँ' : 'Notification preferences'),
                subtitle: Text(hi ? 'इस डिवाइस पर पुश नोटिफिकेशन नियंत्रित करें' : 'Control push notifications on this device'),
                trailing: const Icon(Icons.chevron_right),
                onTap: _openNotificationPreferences,
              ),
              const Divider(height: 1, indent: 16, endIndent: 16),
              ListTile(
                leading: const Icon(Icons.card_giftcard_outlined, color: _Ui.violet),
                title: Text(hi ? 'शेयर करें और कमाएँ' : 'Share & earn'),
                subtitle: Text(hi ? 'दोस्तों को आमंत्रित करें और ₹200 वॉलेट क्रेडिट पाएँ' : 'Invite friends and earn ₹200 wallet credit'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const AccountReferralsScreen()),
                ),
              ),
              const Divider(height: 1, indent: 16, endIndent: 16),
              ListTile(
                leading: const Icon(Icons.tune_rounded, color: _Ui.violet),
                title: Text(hi ? 'ऐप प्राथमिकताएँ' : 'App preferences'),
                subtitle: Text(hi ? 'भाषा सेटिंग' : 'Language settings'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const AccountPreferencesScreen()),
                ),
              ),
              const Divider(height: 1, indent: 16, endIndent: 16),
              ListTile(
                leading: const Icon(Icons.security_outlined, color: _Ui.violet),
                title: Text(hi ? 'पासवर्ड और सुरक्षा' : 'Password & security'),
                subtitle: Text(hi ? 'अपने खाते का पासवर्ड बदलें या सेट करें' : 'Change or set your account password'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const AccountSecurityScreen()),
                ),
              ),
              const Divider(height: 1, indent: 16, endIndent: 16),
              ListTile(
                leading: const Icon(Icons.description_outlined, color: _Ui.violet),
                title: Text(hi ? 'नियम और गोपनीयता' : 'Terms & Privacy'),
                subtitle: Text(hi ? 'AIRway के नियम और गोपनीयता जानकारी पढ़ें' : 'Read AIRway terms and privacy information'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const LegalDocumentsScreen()),
                ),
              ),
              const Divider(height: 1, indent: 16, endIndent: 16),
              ListTile(
                leading: const Icon(Icons.person_off_outlined, color: _Ui.violet),
                title: Text(hi ? 'खाता हटाने का अनुरोध' : 'Delete account'),
                subtitle: Text(hi ? 'अपना AIRway खाता बंद करने का अनुरोध भेजें' : 'Submit a request to close your AIRway account'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const AccountDeletionScreen()),
                ),
              ),
              const Divider(height: 1, indent: 16, endIndent: 16),
              ListTile(
                leading: const Icon(Icons.support_agent_outlined, color: _Ui.violet),
                title: Text(hi ? 'मदद और सहायता' : 'Help & Support'),
                subtitle: Text(hi ? 'बुकिंग, पते और भुगतान में सहायता' : 'Guidance for bookings, addresses and payments'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => HelpSupportScreen(
                      onPrimaryAction: () => setState(() => _tab = 1),
                      onSecondaryAction: () => Navigator.of(context).push(
                        MaterialPageRoute(builder: (_) => const PaymentOptionsScreen()),
                      ),
                    ),
                  ),
                ),
              ),
              const Divider(height: 1, indent: 16, endIndent: 16),
              ListTile(
                leading: const Icon(Icons.refresh_rounded, color: _Ui.violet),
                title: Text(hi ? 'खाते की जानकारी रीफ़्रेश करें' : 'Refresh account data'),
                onTap: _refresh,
              ),
              const Divider(height: 1, indent: 16, endIndent: 16),
              ListTile(
                leading: const Icon(Icons.logout_rounded, color: _Ui.violet),
                title: Text(hi ? 'लॉग आउट' : 'Log out'),
                onTap: _logout,
              ),
            ],
          ),
        ),
      ],
    );
  }

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


/// Compact AIRway brand built only from the supplied original logo artwork.
class _AnimatedAirwayBrand extends StatefulWidget {
  const _AnimatedAirwayBrand();

  @override
  State<_AnimatedAirwayBrand> createState() => _AnimatedAirwayBrandState();
}

class _AnimatedAirwayBrandState extends State<_AnimatedAirwayBrand>
    with SingleTickerProviderStateMixin {
  static const _growthDuration = Duration(milliseconds: 3600);

  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: _growthDuration,
  );

  @override
  void initState() {
    super.initState();
    _controller.forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  double _leafProgress(double startMs) {
    final totalMs = _growthDuration.inMilliseconds.toDouble();
    final start = (startMs / totalMs).clamp(0.0, 1.0).toDouble();
    final end = ((startMs + 520) / totalMs).clamp(0.0, 1.0).toDouble();
    if (_controller.value <= start) return 0;
    return Curves.easeOutBack.transform(
      Interval(start, end > start ? end : 1).transform(_controller.value),
    ).clamp(0.0, 1.0).toDouble();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      height: 80,
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, _) {
          final vineProgress = Curves.easeInOutCubic.transform(
            Interval(0.08, 0.94).transform(_controller.value),
          );
          return Stack(
            fit: StackFit.expand,
            clipBehavior: Clip.hardEdge,
            children: [
              Align(
                alignment: Alignment.centerLeft,
                child: SizedBox(
                  width: 48,
                  height: 54,
                  child: CustomPaint(
                    painter: _AirwaySymbolPainter(
                      innerLeafProgress: _leafProgress(260),
                    ),
                  ),
                ),
              ),
              Align(
                alignment: Alignment.centerRight,
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  child: Text(
                    'AIRway',
                    maxLines: 1,
                    style: const TextStyle(
                      fontFamily: 'Georgia',
                      fontSize: 32,
                      fontWeight: FontWeight.w500,
                      letterSpacing: 0.5,
                      height: 1,
                      color: Color(0xFF1A1917),
                    ),
                  ),
                ),
              ),
              Positioned.fill(
                child: IgnorePointer(
                  child: CustomPaint(
                    painter: _AirwayVinePainter(
                      vineProgress: vineProgress,
                      leaf1Progress: _leafProgress(760),
                      leaf2Progress: _leafProgress(1180),
                      leaf3Progress: _leafProgress(1630),
                      leaf4Progress: _leafProgress(2070),
                      leaf5Progress: _leafProgress(2500),
                      leaf6Progress: _leafProgress(2920),
                    ),
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _AirwaySymbolPainter extends CustomPainter {
  const _AirwaySymbolPainter({required this.innerLeafProgress});

  final double innerLeafProgress;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    canvas.scale(size.width / 100, size.height / 110);

    final ink = Paint()
      ..color = const Color(0xFF1A1917)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 4
      ..strokeJoin = StrokeJoin.round;
    final brown = Paint()..color = const Color(0xFFA88468);
    final green = Paint()
      ..color = const Color(0xFF6F8669)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 7;
    final fineInk = Paint()
      ..color = const Color(0xFF1A1917)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3
      ..strokeJoin = StrokeJoin.round;

    final roof = Path()
      ..moveTo(10, 35)
      ..lineTo(50, 10)
      ..lineTo(90, 35)
      ..lineTo(85, 42)
      ..lineTo(50, 20)
      ..lineTo(15, 42)
      ..close();
    canvas.drawPath(roof, brown);
    canvas.drawPath(roof, ink);

    for (final rect in <Rect>[
      const Rect.fromLTWH(16, 38, 12, 54),
      const Rect.fromLTWH(72, 38, 12, 54),
    ]) {
      canvas.drawRect(rect, brown);
      canvas.drawRect(rect, ink);
    }

    final outerArch = Path()
      ..moveTo(28, 92)
      ..lineTo(28, 52)
      ..cubicTo(28, 27.7, 72, 27.7, 72, 52)
      ..lineTo(72, 92);
    canvas.drawPath(outerArch, green);
    canvas.drawPath(outerArch, fineInk);

    final innerArch = Path()
      ..moveTo(35, 92)
      ..lineTo(35, 53)
      ..cubicTo(35, 36.4, 65, 36.4, 65, 53)
      ..lineTo(65, 92);
    canvas.drawPath(innerArch, fineInk);

    final sill = Rect.fromLTWH(16, 92, 68, 10);
    canvas.drawRect(sill, brown);
    canvas.drawRect(sill, ink);

    final stem = Path()
      ..moveTo(40, 92)
      ..quadraticBezierTo(40, 72, 54, 66);
    canvas.drawPath(
      stem,
      Paint()
        ..color = const Color(0xFF1A1917)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 3.5
        ..strokeCap = StrokeCap.round,
    );

    canvas.save();
    canvas.translate(51, 69);
    canvas.scale(0.2 + (0.8 * innerLeafProgress));
    final leaf = Path()
      ..moveTo(-7, 7)
      ..cubicTo(-7, -5, 7, -7, 7, -7)
      ..cubicTo(7, -7, 7, 7, -7, 7)
      ..close();
    canvas.drawPath(leaf, Paint()..color = const Color(0xFF7C9674));
    canvas.drawPath(
      leaf,
      Paint()
        ..color = const Color(0xFF1A1917)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 3,
    );
    canvas.restore();
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _AirwaySymbolPainter oldDelegate) =>
      oldDelegate.innerLeafProgress != innerLeafProgress;
}

class _AirwayVinePainter extends CustomPainter {
  const _AirwayVinePainter({
    required this.vineProgress,
    required this.leaf1Progress,
    required this.leaf2Progress,
    required this.leaf3Progress,
    required this.leaf4Progress,
    required this.leaf5Progress,
    required this.leaf6Progress,
  });

  final double vineProgress;
  final double leaf1Progress;
  final double leaf2Progress;
  final double leaf3Progress;
  final double leaf4Progress;
  final double leaf5Progress;
  final double leaf6Progress;

  static const _stem = Color(0xFF496B43);
  static const _stemLight = Color(0xFF78966A);
  static const _leafDark = Color(0xFF477348);
  static const _leafLight = Color(0xFFA8C58B);
  static const _outline = Color(0xFF426443);

  void _drawGrowingPath(Canvas canvas, Path path, double progress) {
    if (progress <= 0) return;
    final metrics = path.computeMetrics();
    for (final metric in metrics) {
      final visible = metric.extractPath(
        0,
        metric.length * progress.clamp(0.0, 1.0).toDouble(),
      );
      canvas.drawPath(
        visible,
        Paint()
          ..color = _stem.withAlpha(45)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 5.2
          ..strokeCap = StrokeCap.round
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 2),
      );
      canvas.drawPath(
        visible,
        Paint()
          ..color = _stem
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2.7
          ..strokeCap = StrokeCap.round
          ..strokeJoin = StrokeJoin.round,
      );
      canvas.drawPath(
        visible,
        Paint()
          ..color = _stemLight.withAlpha(175)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 0.85
          ..strokeCap = StrokeCap.round,
      );
    }
  }

  Path _leafShape() => Path()
    ..moveTo(0, 0)
    ..cubicTo(4, -10, 15, -15, 24, -9)
    ..cubicTo(27, 0, 17, 10, 0, 0)
    ..close();

  void _drawLeaf(
    Canvas canvas,
    Offset origin,
    double progress,
    double rotation,
    double scale,
  ) {
    if (progress <= 0) return;

    canvas.save();
    canvas.translate(origin.dx, origin.dy);
    canvas.rotate(rotation);
    final pop = Curves.easeOutBack.transform(progress).clamp(0.0, 1.08).toDouble();
    canvas.scale(scale * pop);

    final leaf = _leafShape();
    final bounds = leaf.getBounds();

    canvas.drawPath(
      leaf,
      Paint()
        ..color = const Color(0xFF244A2D).withAlpha(35)
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 2.2),
    );
    canvas.drawPath(
      leaf,
      Paint()
        ..shader = const LinearGradient(
          begin: Alignment.bottomLeft,
          end: Alignment.topRight,
          colors: [_leafDark, Color(0xFF6F9A5D), _leafLight],
          stops: [0, 0.58, 1],
        ).createShader(bounds),
    );
    canvas.drawPath(
      leaf,
      Paint()
        ..color = _outline.withAlpha(180)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 0.75,
    );

    // A fine midrib and two delicate side veins make the leaves feel botanical.
    final veins = Path()
      ..moveTo(1.5, -0.2)
      ..quadraticBezierTo(11, -4.5, 23, -8.5)
      ..moveTo(8, -3)
      ..quadraticBezierTo(9, -7, 7, -9)
      ..moveTo(14, -5)
      ..quadraticBezierTo(17, -8, 18, -10);
    canvas.drawPath(
      veins,
      Paint()
        ..color = const Color(0xFFD8E7C4).withAlpha(185)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 0.65
        ..strokeCap = StrokeCap.round,
    );
    canvas.restore();
  }

  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    canvas.scale(size.width / 310, size.height / 80);

    // The main stem grows out from the little plant inside the house arch,
    // then travels in a relaxed, organic arc above the AIRway wordmark.
    final mainStem = Path()
      ..moveTo(31, 55)
      ..cubicTo(49, 54, 61, 43, 79, 40)
      ..cubicTo(103, 35, 119, 48, 143, 39)
      ..cubicTo(166, 30, 178, 17, 204, 20)
      ..cubicTo(226, 22, 237, 31, 254, 23)
      ..cubicTo(270, 15, 282, 13, 292, 22)
      ..cubicTo(301, 31, 295, 40, 286, 37)
      ..cubicTo(281, 35, 281, 31, 285, 29);

    _drawGrowingPath(canvas, mainStem, vineProgress);

    // Fine side shoots branch naturally from the main vine.
    final shoots = <Path>[
      Path()
        ..moveTo(76, 41)
        ..cubicTo(78, 33, 83, 27, 92, 23),
      Path()
        ..moveTo(139, 40)
        ..cubicTo(143, 31, 149, 25, 159, 22),
      Path()
        ..moveTo(199, 20)
        ..cubicTo(202, 13, 207, 9, 215, 7),
      Path()
        ..moveTo(251, 24)
        ..cubicTo(255, 17, 261, 13, 269, 12),
    ];
    for (var i = 0; i < shoots.length; i++) {
      final threshold = 0.22 + (i * 0.16);
      final shootProgress =
          ((vineProgress - threshold) / (1 - threshold)).clamp(0.0, 1.0).toDouble();
      _drawGrowingPath(canvas, shoots[i], Curves.easeOut.transform(shootProgress));
    }

    _drawLeaf(canvas, const Offset(61, 45), leaf1Progress, -0.78, 0.72);
    _drawLeaf(canvas, const Offset(91, 24), leaf2Progress, -0.95, 0.68);
    _drawLeaf(canvas, const Offset(151, 29), leaf3Progress, -0.82, 0.72);
    _drawLeaf(canvas, const Offset(211, 13), leaf4Progress, -0.9, 0.66);
    _drawLeaf(canvas, const Offset(263, 18), leaf5Progress, -0.8, 0.7);
    _drawLeaf(canvas, const Offset(287, 36), leaf6Progress, 2.35, 0.58);

    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _AirwayVinePainter oldDelegate) =>
      oldDelegate.vineProgress != vineProgress ||
      oldDelegate.leaf1Progress != leaf1Progress ||
      oldDelegate.leaf2Progress != leaf2Progress ||
      oldDelegate.leaf3Progress != leaf3Progress ||
      oldDelegate.leaf4Progress != leaf4Progress ||
      oldDelegate.leaf5Progress != leaf5Progress ||
      oldDelegate.leaf6Progress != leaf6Progress;
}
