import 'package:flutter/material.dart';
import 'package:airway/core/storage/secure_session_storage.dart';
import 'package:airway/features/catalog/data/catalog_api.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';
import 'package:airway/features/booking/data/booking_api.dart';
import 'package:airway/features/booking/presentation/customer_cart_screen.dart';

class _Ui {
  static const violet = Color(0xFF315C46);
  static const ink = Color(0xFF1E2923);
  static const sub = Color(0xFF748078);
  static const bg = Color(0xFFFFFFFF);
  static const line = Color(0xFFEAE6DE);
}

class BookingScheduledScreen extends StatefulWidget {
  final int serviceId;
  final String serviceTitle;
  final int? addressId;
  final Map<String, dynamic> initialCategoryAnswers;

  const BookingScheduledScreen({
    super.key,
    required this.serviceId,
    required this.serviceTitle,
    this.addressId,
    this.initialCategoryAnswers = const {},
  });

  @override
  State<BookingScheduledScreen> createState() => _BookingScheduledScreenState();
}

class _BookingScheduledScreenState extends State<BookingScheduledScreen> {
  Service? _service;
  bool _loading = true;
  String? _error;

  // Availability state

  // Selection state
  int? _selectedVariantId;
  List<int> _selectedAddonIds = [];
  final Map<String, dynamic> _formAnswers = {};
  final Map<String, dynamic> _categoryAnswers = {};
  int? _selectedAddressId;
  bool _addressCheckBusy = false;
  List<Map<String, dynamic>> _addresses = [];
  int _quantity = 1;
  int _flowStep = 0;
  final _formKey = GlobalKey<FormState>();

  // Summary state
  double _subtotal = 0;
  double _estimatedTotal = 0;

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final addresses = await _loadAddresses();
      final defaultAddress = addresses.firstWhere(
        (a) => a['is_default'] == true,
        orElse: () => addresses.isNotEmpty ? addresses[0] : <String, dynamic>{},
      );
      final selectedAddressId =
          widget.addressId ?? (defaultAddress.isEmpty ? null : defaultAddress['id']) as int?;
      final service = await CatalogApi.getService(
        widget.serviceId,
        addressId: selectedAddressId,
      );

      if (!mounted) return;

      setState(() {
        _service = service;
        _addresses = addresses;
        _selectedAddressId = selectedAddressId;
        _categoryAnswers.addAll(widget.initialCategoryAnswers);
        _loading = false;

        // Auto-select first variant if exactly one exists.
        if (service.variants.length == 1) {
          _selectedVariantId = service.variants[0].id;
        }
      });
      _updateSummary();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  Future<void> _changeAddress(int addressId) async {
    if (addressId == _selectedAddressId) return;
    setState(() => _addressCheckBusy = true);
    try {
      final service = await CatalogApi.getService(
        widget.serviceId,
        addressId: addressId,
      );
      if (!mounted) return;
      setState(() {
        _selectedAddressId = addressId;
        _service = service;
        _selectedVariantId = service.variants.length == 1
            ? service.variants.first.id
            : null;
        _selectedAddonIds.clear();
        _formAnswers.clear();
        _categoryAnswers
          ..clear()
          ..addAll(widget.initialCategoryAnswers);
        _addressCheckBusy = false;
      });
      _updateSummary();
    } catch (e) {
      if (!mounted) return;
      setState(() => _addressCheckBusy = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'This service is not available at the selected address. $e',
          ),
        ),
      );
    }
  }

  Future<List<Map<String, dynamic>>> _loadAddresses() async {
    final session = await SecureSessionStorage.readSession();
    if (session == null) return [];

    try {
      final result = await BookingApi.request('/api/v1/auth/addresses/');
      final raw = result is List ? result : (result is Map ? result['results'] : null);
      if (raw is! List) return [];
      return raw.map((e) => Map<String, dynamic>.from(e as Map)).toList();
    } catch (_) {
      return [];
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _Ui.bg,
      appBar: AppBar(
        title: Text(widget.serviceTitle),
        backgroundColor: _Ui.bg,
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: _Ui.violet))
          : _error != null
              ? _errorWidget(_error!)
              : _service == null
                  ? _errorWidget('Service not found.')
                  : _buildBody(),
    );
  }

  List<String> _flowSteps(Service service) => [
    if (service.variants.isNotEmpty) 'Package',
    if (service.formFields.isNotEmpty) 'Your Space',
    if (service.addons.isNotEmpty) 'Add-ons',
    'Address',
    'Summary',
  ];

  String _stepSubtitle(String step) {
    switch (step) {
      case 'Package':
        return 'Choose the service package that suits your needs.';
      case 'Your Space':
        return 'Tell us a little about the space and service requirements.';
      case 'Add-ons':
        return 'Personalize your booking with optional extras.';
      case 'Address':
        return 'Where should our service professional visit?';
      default:
        return 'Review your selections before adding this service to your cart.';
    }
  }

  void _continueFlow() {
    final service = _service!;
    final steps = _flowSteps(service);
    final current = steps[_flowStep];
    if (current == 'Package' &&
        service.variants.isNotEmpty &&
        _selectedVariantId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please choose a package to continue.')),
      );
      return;
    }
    if (current == 'Your Space') {
      for (final field in service.formFields) {
        if (field.isRequired &&
            (_formAnswers[field.key] == null ||
                _formAnswers[field.key].toString().trim().isEmpty)) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Please complete: ${field.label}')),
          );
          return;
        }
      }
    }
    if (current == 'Address' && _selectedAddressId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please select a service address.')),
      );
      return;
    }
    if (_flowStep < steps.length - 1) {
      setState(() => _flowStep++);
    } else {
      _addToCart();
    }
  }

  Widget _buildBody() {
    final service = _service!;
    final steps = _flowSteps(service);
    if (_flowStep >= steps.length) _flowStep = steps.length - 1;
    final step = steps[_flowStep];
    final isLast = _flowStep == steps.length - 1;
    final slivers = <Widget>[
      if ((service.image?.isNotEmpty ?? false) || service.images.isNotEmpty)
        _imageSliver(
          service.image?.isNotEmpty == true
              ? service.image
              : service.images.first.image,
        ),
      SliverToBoxAdapter(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 18, 20, 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Text(
                    'STEP ${_flowStep + 1} OF ${steps.length}',
                    style: const TextStyle(
                      color: _Ui.violet,
                      fontSize: 10,
                      fontWeight: FontWeight.w900,
                      letterSpacing: 1.2,
                    ),
                  ),
                  const Spacer(),
                  Text(
                    '${((_flowStep + 1) / steps.length * 100).round()}% complete',
                    style: const TextStyle(color: _Ui.sub, fontSize: 11),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Row(
                children: List.generate(steps.length, (index) {
                  final active = index <= _flowStep;
                  return Expanded(
                    child: Container(
                      height: 5,
                      margin: EdgeInsets.only(right: index == steps.length - 1 ? 0 : 5),
                      decoration: BoxDecoration(
                        color: active ? _Ui.violet : _Ui.line,
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                  );
                }),
              ),
              const SizedBox(height: 20),
              Text(
                step,
                style: const TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.w900,
                  color: _Ui.ink,
                ),
              ),
              const SizedBox(height: 5),
              Text(
                _stepSubtitle(step),
                style: const TextStyle(color: _Ui.sub, fontSize: 13, height: 1.4),
              ),
            ],
          ),
        ),
      ),
    ];

    switch (step) {
      case 'Package':
        slivers.addAll([
          _sectionHeader('Choose your package'),
          _variantPicker(),
        ]);
        break;
      case 'Your Space':
        slivers.addAll([
          _sectionHeader('About your space'),
          _formFields(),
        ]);
        break;
      case 'Add-ons':
        slivers.addAll([
          _sectionHeader('Optional extras'),
          _addonPicker(),
        ]);
        break;
      case 'Address':
        slivers.addAll([
          _sectionHeader('Select service address'),
          _addressPicker(),
        ]);
        break;
      case 'Summary':
        slivers.addAll([
          _sectionHeader('Your service'),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              child: Row(
                children: [
                  IconButton(
                    onPressed: _quantity > 1
                        ? () => setState(() => _quantity--)
                        : null,
                    icon: const Icon(Icons.remove_circle_outline),
                  ),
                  Text('$_quantity', style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
                  IconButton(
                    onPressed: _quantity < 20
                        ? () => setState(() => _quantity++)
                        : null,
                    icon: const Icon(Icons.add_circle_outline),
                  ),
                  const Spacer(),
                  const Text('Maximum 20', style: TextStyle(color: _Ui.sub, fontSize: 11)),
                ],
              ),
            ),
          ),
          _sectionHeader('Price details'),
          _summaryCard(),
        ]);
        break;
    }

    slivers.add(
      SliverToBoxAdapter(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 22, 20, 28),
          child: SafeArea(
            top: false,
            child: Row(
              children: [
                if (_flowStep > 0) ...[
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () => setState(() => _flowStep--),
                      child: const Text('Back'),
                    ),
                  ),
                  const SizedBox(width: 10),
                ],
                Expanded(
                  flex: 2,
                  child: FilledButton(
                    onPressed: _addressCheckBusy || (step == 'Address' && _selectedAddressId == null)
                        ? null
                        : _continueFlow,
                    child: Text(isLast ? 'Add to Cart' : 'Continue'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );

    return CustomScrollView(slivers: slivers);
  }

  Widget _imageSliver(String? imageUrl) {
    if (imageUrl == null || imageUrl.isEmpty) {
      return const SliverToBoxAdapter(child: SizedBox(height: 20));
    }
    return SliverToBoxAdapter(
      child: Container(
        height: 160,
        decoration: BoxDecoration(
          image: DecorationImage(
            image: NetworkImage(imageUrl),
            fit: BoxFit.cover,
          ),
        ),
      ),
    );
  }

  Widget _sectionHeader(String title) {
    return SliverToBoxAdapter(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
        child: Text(
          title,
          style: const TextStyle(
            fontSize: 17,
            fontWeight: FontWeight.w800,
            color: _Ui.ink,
          ),
        ),
      ),
    );
  }

  Widget _addressPicker() {
    if (_addresses.isEmpty) {
      return const SliverToBoxAdapter(
        child: Padding(
          padding: EdgeInsets.all(20),
          child: Text(
            'No addresses saved. Please add an address first.',
            style: TextStyle(color: _Ui.sub),
          ),
        ),
      );
    }

    return SliverToBoxAdapter(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: Wrap(
          spacing: 12,
          runSpacing: 12,
          children: _addresses.map((addr) {
            final isSelected = addr['id'] == _selectedAddressId;
            return GestureDetector(
              onTap: _addressCheckBusy
                  ? null
                  : () => _changeAddress(addr['id'] as int),
              child: Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: isSelected ? _Ui.violet : _Ui.line,
                    width: isSelected ? 2 : 1,
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(
                          Icons.location_on,
                          size: 16,
                          color: isSelected ? _Ui.violet : _Ui.sub,
                        ),
                        const SizedBox(width: 6),
                        Expanded(
                          child: Text(
                            addr['label'] ?? 'Home',
                            style: TextStyle(
                              fontWeight: FontWeight.w600,
                              color: isSelected ? _Ui.violet : _Ui.ink,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      addr['full_address'] ?? '',
                      style: const TextStyle(
                        fontSize: 12,
                        color: _Ui.sub,
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
            );
          }).toList(),
        ),
      ),
    );
  }

  Widget _variantPicker() {
    final service = _service!;
    return SliverToBoxAdapter(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: Wrap(
          spacing: 12,
          runSpacing: 12,
          children: service.variants.map((variant) {
            final isSelected = variant.id == _selectedVariantId;
            return GestureDetector(
              onTap: () {
                setState(() {
                  _selectedVariantId = variant.id;
                });
                _updateSummary();
              },
              child: Container(
                width: MediaQuery.of(context).size.width * 0.48,
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                    color: isSelected ? _Ui.violet : _Ui.line,
                    width: isSelected ? 2 : 1,
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      variant.title,
                      style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                        color: _Ui.ink,
                      ),
                    ),
                    if (variant.durationMinutes != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Text(
                          '${variant.durationMinutes} min',
                          style: const TextStyle(
                            fontSize: 12,
                            color: _Ui.sub,
                          ),
                        ),
                      ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        if (variant.mrp > variant.price)
                          Text(
                            '₹${variant.mrp.toStringAsFixed(0)}',
                            style: const TextStyle(
                              fontSize: 12,
                              decoration: TextDecoration.lineThrough,
                              color: _Ui.sub,
                            ),
                          ),
                        const Spacer(),
                        Text(
                          '₹${variant.price.toStringAsFixed(0)}',
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w800,
                            color: _Ui.violet,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            );
          }).toList(),
        ),
      ),
    );
  }

  Widget _addonPicker() {
    final service = _service!;
    return SliverToBoxAdapter(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: Column(
          children: service.addons.map((addon) {
            final isSelected = _selectedAddonIds.contains(addon.id);
            return InkWell(
              onTap: () {
                setState(() {
                  if (isSelected) {
                    _selectedAddonIds.remove(addon.id);
                  } else {
                    _selectedAddonIds.add(addon.id);
                  }
                });
                _updateSummary();
              },
              child: Container(
                margin: const EdgeInsets.only(bottom: 8),
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: isSelected ? _Ui.violet : _Ui.line,
                  ),
                ),
                child: Row(
                  children: [
                    Container(
                      width: 24,
                      height: 24,
                      decoration: BoxDecoration(
                        color: isSelected ? _Ui.violet : Colors.transparent,
                        border: Border.all(color: _Ui.violet),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: isSelected
                          ? const Icon(Icons.check, color: Colors.white, size: 16)
                          : null,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        addon.title,
                        style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                          color: _Ui.ink,
                        ),
                      ),
                    ),
                    Text(
                      '₹${addon.price.toStringAsFixed(0)}',
                      style: const TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                        color: _Ui.violet,
                      ),
                    ),
                  ],
                ),
              ),
            );
          }).toList(),
        ),
      ),
    );
  }

  Widget _formFields() {
    final fields = _service!.formFields;
    return SliverToBoxAdapter(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: Column(
          children: fields.map((field) {
            final decoration = InputDecoration(
              labelText: field.isRequired ? '${field.label} *' : field.label,
              filled: true,
              fillColor: Colors.white,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(14),
                borderSide: BorderSide(color: _Ui.line),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(14),
                borderSide: BorderSide(color: _Ui.line),
              ),
            );
            Widget input;
            switch (field.fieldType) {
              case 'select':
                input = DropdownButtonFormField<String>(
                  value: _formAnswers[field.key]?.toString(),
                  decoration: decoration,
                  items: field.options.map((option) {
                    final value = option.toString();
                    return DropdownMenuItem(value: value, child: Text(value));
                  }).toList(),
                  onChanged: (value) => setState(() => _formAnswers[field.key] = value),
                );
                break;
              case 'photo':
                input = TextFormField(
                  initialValue: _formAnswers[field.key]?.toString() ?? '',
                  decoration: decoration.copyWith(hintText: 'Paste an image URL'),
                  keyboardType: TextInputType.url,
                  onChanged: (value) => _formAnswers[field.key] = value,
                );
                break;
              default:
                input = TextFormField(
                  initialValue: _formAnswers[field.key]?.toString() ?? '',
                  decoration: decoration,
                  keyboardType: field.fieldType == 'number'
                      ? TextInputType.number
                      : TextInputType.text,
                  maxLines: field.fieldType == 'textarea' ? 3 : 1,
                  onChanged: (value) => _formAnswers[field.key] = value,
                );
            }
            return Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: input,
            );
          }).toList(),
        ),
      ),
    );
  }

  Widget _summaryCard() {
    final service = _service!;
    return SliverToBoxAdapter(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: _Ui.line),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                service.title,
                style: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: _Ui.ink,
                ),
              ),
              if (_selectedVariantId != null) ...[
                const SizedBox(height: 8),
                Row(
                  children: [
                    const Icon(Icons.info_outline, size: 14, color: _Ui.sub),
                    const SizedBox(width: 4),
                    Expanded(
                      child: Text(
                        'Package: ${service.variants.firstWhere((v) => v.id == _selectedVariantId, orElse: () => service.variants.first).title}',
                        style: const TextStyle(fontSize: 13, color: _Ui.sub),
                      ),
                    ),
                  ],
                ),
              ],
              const Divider(height: 16),
              Row(
                children: [
                  const Text('Subtotal', style: TextStyle(color: _Ui.sub)),
                  const Spacer(),
                  Text(
                    '₹${(_subtotal * _quantity).toStringAsFixed(0)}',
                    style: const TextStyle(color: _Ui.sub),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Row(
                children: [
                  const Text('Est. total (incl. tax)', style: TextStyle(fontWeight: FontWeight.w700, color: _Ui.ink)),
                  const Spacer(),
                  Text(
                    '₹${(_estimatedTotal * _quantity).toStringAsFixed(0)}',
                    style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w800,
                      color: _Ui.violet,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              const Text(
                'Final amount confirmed by backend after booking',
                style: TextStyle(fontSize: 11, color: _Ui.sub),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _updateSummary() {
    final service = _service!;
    final variant = service.variants.firstWhere(
      (v) => v.id == _selectedVariantId,
      orElse: () => service.variants.isEmpty
          ? ServiceVariant(id: 0, title: '', mrp: 0, price: 0, discountPercent: 0, sortOrder: 0, isActive: false)
          : service.variants.first,
    );
    double total = service.variants.isEmpty ? service.visitFee : variant.price;

    for (final addonId in _selectedAddonIds) {
      final addon = service.addons.firstWhere(
        (a) => a.id == addonId,
        orElse: () => AddOn(id: 0, title: '', mrp: 0, price: 0, discountPercent: 0, sortOrder: 0, isActive: false),
      );
      total += addon.price;
    }

    _subtotal = total;
    _estimatedTotal = total * 1.18; // Estimate only; backend confirms final amount
  }

  Future<void> _addToCart() async {
    if (_selectedAddressId == null) return;
    if (_service!.variants.isNotEmpty && _selectedVariantId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please choose a package.')),
      );
      return;
    }
    for (final field in _service!.formFields) {
      if (field.isRequired &&
          (_formAnswers[field.key] == null ||
              _formAnswers[field.key].toString().trim().isEmpty)) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Please complete: ${field.label}')),
        );
        return;
      }
    }
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (_) => const Center(child: CircularProgressIndicator()),
    );
    try {
      await BookingApi.updateCartAddress(_selectedAddressId);
      final addonSelections = _selectedAddonIds
          .map((id) => {'id': id, 'quantity': 1})
          .toList();
      await BookingApi.addCartItem(
        serviceId: widget.serviceId,
        variantId: _selectedVariantId,
        quantity: _quantity,
        addonSelections: addonSelections,
        formAnswers: _formAnswers,
        categoryAnswers: _categoryAnswers,
      );
      if (!mounted) return;
      Navigator.pop(context);
      Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => const CustomerCartScreen()),
      );
    } catch (e) {
      if (!mounted) return;
      Navigator.pop(context);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not add service to cart: $e')),
      );
    }
  }

  Widget _errorWidget(String message) => Center(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, color: Colors.redAccent, size: 52),
              const SizedBox(height: 14),
              Text(
                message,
                textAlign: TextAlign.center,
                style: const TextStyle(color: _Ui.sub),
              ),
              const SizedBox(height: 20),
              FilledButton(
                onPressed: _loadData,
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      );
}