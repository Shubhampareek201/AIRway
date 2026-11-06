import 'package:flutter/material.dart';
import 'package:airway/core/storage/secure_session_storage.dart';
import 'package:airway/features/catalog/data/catalog_api.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';
import 'package:airway/features/booking/data/booking_api.dart';
import 'package:airway/features/booking/presentation/customer_cart_screen.dart';

class _Ui {
  static const violet = Color(0xFF7861A8);
  static const ink = Color(0xFF292331);
  static const sub = Color(0xFF81788A);
  static const bg = Color(0xFFF7F3EC);
  static const line = Color(0xFFE8E0ED);
}

class BookingScheduledScreen extends StatefulWidget {
  final int serviceId;
  final String serviceTitle;

  const BookingScheduledScreen({
    super.key,
    required this.serviceId,
    required this.serviceTitle,
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
  int? _selectedAddressId;
  List<Map<String, dynamic>> _addresses = [];
  int _quantity = 1;
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
      final service = await CatalogApi.getService(widget.serviceId);
      final addresses = await _loadAddresses();

      if (!mounted) return;

      setState(() {
        _service = service;
        _addresses = addresses;
        _selectedAddressId = addresses.isNotEmpty ? addresses[0]['id'] : null;
        _loading = false;

        // Auto-select first variant if exactly one exists
        if (service.variants.length == 1) {
          _selectedVariantId = service.variants[0].id;
        }

      });

    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
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

  Widget _buildBody() {
    final service = _service!;
    return Form(
      key: _formKey,
      child: CustomScrollView(
        slivers: [
          if (service.image?.isNotEmpty ?? false) _imageSliver(service.image),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 4),
              child: Text(
                'Customize your service',
                style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w900, color: _Ui.ink),
              ),
            ),
          ),
          _sectionHeader('Select Address'),
          _addressPicker(),
          if (service.variants.isNotEmpty) ...[
            _sectionHeader('Choose a Package'),
            _variantPicker(),
          ],
          if (service.addons.isNotEmpty) ...[
            _sectionHeader('Optional Add-ons'),
            _addonPicker(),
          ],
          if (service.formFields.isNotEmpty) ...[
            _sectionHeader('A Few Details'),
            _formFields(),
          ],
          _sectionHeader('Quantity'),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              child: Row(
                children: [
                  IconButton(
                    onPressed: _quantity > 1 ? () => setState(() => _quantity--) : null,
                    icon: const Icon(Icons.remove_circle_outline),
                  ),
                  Text('$_quantity', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
                  IconButton(
                    onPressed: _quantity < 20 ? () => setState(() => _quantity++) : null,
                    icon: const Icon(Icons.add_circle_outline),
                  ),
                  const Spacer(),
                  const Text('Maximum 20', style: TextStyle(color: _Ui.sub, fontSize: 12)),
                ],
              ),
            ),
          ),
          _sectionHeader('Price Summary'),
          _summaryCard(),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
              child: SafeArea(
                top: false,
                child: FilledButton.icon(
                  onPressed: _selectedAddressId == null ? null : _addToCart,
                  icon: const Icon(Icons.add_shopping_cart_rounded),
                  label: const Text('Add to Cart'),
                ),
              ),
            ),
          ),
        ],
      ),
    );
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
              onTap: () {
                setState(() => _selectedAddressId = addr['id']);
              },
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
                input = Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    border: Border.all(color: _Ui.line),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: const Text(
                    'Photo upload is not available in this app version.',
                    style: TextStyle(color: _Ui.sub, fontSize: 13),
                  ),
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
          SnackBar(content: Text('Please complete: \${field.label}')),
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