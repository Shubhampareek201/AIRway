import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:airway/features/booking/data/booking_api.dart';
import 'package:airway/features/booking/presentation/customer_cart_screen.dart';
import 'package:airway/features/booking/presentation/customer_cart_badge.dart';
import 'package:airway/features/catalog/data/catalog_api.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';
import 'package:airway/features/catalog/data/catalog_image_resolver.dart';



class _ElectricalAddSelection {
  const _ElectricalAddSelection({
    required this.variant,
    required this.notes,
    required this.photo,
  });

  final ServiceVariant? variant;
  final String notes;
  final File? photo;
}

class _Ui {
  static const violet = Color(0xFF315C46);
  static const ink = Color(0xFF1E2923);
  static const sub = Color(0xFF748078);
  static const bg = Color(0xFFFFFFFF);
  static const line = Color(0xFFEAE6DE);
}

class ServiceDetailScreen extends StatefulWidget {
  final int serviceId;
  final int? addressId;
  final Map<String, dynamic> initialAnswers;
  final bool openElectricalAddOnLoad;
  final Service? initialService;

  const ServiceDetailScreen({
    super.key,
    required this.serviceId,
    this.addressId,
    this.initialAnswers = const {},
    this.openElectricalAddOnLoad = false,
    this.initialService,
  });

  @override
  State<ServiceDetailScreen> createState() => _ServiceDetailScreenState();
}

class _ServiceDetailScreenState extends State<ServiceDetailScreen> {
  Service? _service;
  bool _loading = true;
  String? _error;
  final TextEditingController _electricalNotesController = TextEditingController();
  bool _electricalPopupStarted = false;

  @override
  void initState() {
    super.initState();
    if (widget.initialService != null) {
      _service = widget.initialService;
      _loading = false;
      if (widget.openElectricalAddOnLoad) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted && !_electricalPopupStarted) {
            _electricalPopupStarted = true;
            _addElectricalService(_service!);
          }
        });
      }
    } else {
      _loadService();
    }
  }

  @override
  void dispose() {
    _electricalNotesController.dispose();
    super.dispose();
  }

  Future<void> _loadService() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final service = await CatalogApi.getService(
        widget.serviceId,
        addressId: widget.addressId,
        audience: widget.initialAnswers['beauty_audience']?.toString(),
        categoryAnswers: widget.initialAnswers,
      );
      if (mounted) setState(() => _service = service);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
    if (mounted && widget.openElectricalAddOnLoad && _service != null &&
        !_electricalPopupStarted) {
      _electricalPopupStarted = true;
      await _addElectricalService(_service!);
    }
  }


  Future<void> _addElectricalService(Service service) async {
    final variants = _matchingVariants(service);
    _electricalNotesController.clear();
    final picker = ImagePicker();
    File? selectedPhoto;

    Future<_ElectricalAddSelection?> showElectricalSheet() {
      ServiceVariant? selectedVariant;
      return showModalBottomSheet<_ElectricalAddSelection>(
        context: context,
        isScrollControlled: true,
        backgroundColor: Colors.transparent,
        builder: (sheetContext) => StatefulBuilder(
          builder: (context, setSheetState) {
            final visitFee = service.bookingMode == 'inspection'
                ? service.visitFee
                : 0.0;
            final servicePrice = selectedVariant?.price;
            final total = servicePrice == null ? null : servicePrice + visitFee;

            Future<void> pickPhoto(ImageSource source) async {
              try {
                final picked = await picker.pickImage(
                  source: source,
                  imageQuality: 82,
                  maxWidth: 1600,
                  maxHeight: 1600,
                );
                if (picked != null) {
                  setSheetState(() => selectedPhoto = File(picked.path));
                }
              } catch (error) {
                if (sheetContext.mounted) {
                  ScaffoldMessenger.of(sheetContext).showSnackBar(
                    SnackBar(content: Text('Could not select photo: $error')),
                  );
                }
              }
            }

            return SafeArea(
              child: Container(
                constraints: BoxConstraints(
                  maxHeight: MediaQuery.sizeOf(context).height * 0.90,
                ),
                padding: EdgeInsets.fromLTRB(
                  18, 12, 18, 16 + MediaQuery.viewInsetsOf(context).bottom,
                ),
                decoration: const BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.vertical(top: Radius.circular(26)),
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Center(
                      child: Container(
                        width: 40,
                        height: 4,
                        decoration: BoxDecoration(
                          color: _Ui.line,
                          borderRadius: BorderRadius.circular(8),
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                    Row(
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(service.title, style: const TextStyle(
                                fontSize: 19,
                                fontWeight: FontWeight.w900,
                                color: _Ui.ink,
                              )),
                              const SizedBox(height: 4),
                              const Text(
                                'Choose an option and tell us about the issue',
                                style: TextStyle(fontSize: 12, color: _Ui.sub),
                              ),
                            ],
                          ),
                        ),
                        const Icon(Icons.electrical_services_rounded,
                            color: _Ui.violet, size: 25),
                      ],
                    ),
                    const SizedBox(height: 14),
                    Flexible(
                      child: SingleChildScrollView(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            if (variants.isEmpty)
                              Container(
                                padding: const EdgeInsets.all(14),
                                decoration: BoxDecoration(
                                  color: const Color(0xFFF7F8F6),
                                  borderRadius: BorderRadius.circular(14),
                                  border: Border.all(color: _Ui.line),
                                ),
                                child: const Text(
                                  'Professional assessment required. The final service cost will be confirmed after the issue is checked.',
                                  style: TextStyle(fontSize: 12, height: 1.4, color: _Ui.ink),
                                ),
                              ),
                            for (final variant in variants) ...[
                              InkWell(
                                onTap: () => setSheetState(() => selectedVariant = variant),
                                borderRadius: BorderRadius.circular(15),
                                child: Container(
                                  padding: const EdgeInsets.all(13),
                                  decoration: BoxDecoration(
                                    color: selectedVariant?.id == variant.id
                                        ? const Color(0xFFEAF1EA)
                                        : Colors.white,
                                    borderRadius: BorderRadius.circular(15),
                                    border: Border.all(
                                      color: selectedVariant?.id == variant.id
                                          ? _Ui.violet
                                          : _Ui.line,
                                      width: selectedVariant?.id == variant.id ? 1.7 : 1,
                                    ),
                                  ),
                                  child: Row(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Icon(
                                        selectedVariant?.id == variant.id
                                            ? Icons.radio_button_checked_rounded
                                            : Icons.radio_button_off_rounded,
                                        color: _Ui.violet,
                                        size: 21,
                                      ),
                                      const SizedBox(width: 10),
                                      Expanded(
                                        child: Column(
                                          crossAxisAlignment: CrossAxisAlignment.start,
                                          children: [
                                            Text(variant.title, style: const TextStyle(
                                              fontSize: 14,
                                              fontWeight: FontWeight.w900,
                                              color: _Ui.ink,
                                            )),
                                            if (variant.description?.isNotEmpty == true)
                                              Padding(
                                                padding: const EdgeInsets.only(top: 4),
                                                child: Text(variant.description!,
                                                  style: const TextStyle(fontSize: 11.5, height: 1.35, color: _Ui.sub)),
                                              ),
                                            if (variant.includedTasks.isNotEmpty) ...[
                                              const SizedBox(height: 7),
                                              for (final task in variant.includedTasks)
                                                Padding(
                                                  padding: const EdgeInsets.only(top: 3),
                                                  child: Row(
                                                    crossAxisAlignment: CrossAxisAlignment.start,
                                                    children: [
                                                      const Icon(Icons.check_rounded, size: 14, color: _Ui.violet),
                                                      const SizedBox(width: 5),
                                                      Expanded(child: Text(task,
                                                        style: const TextStyle(fontSize: 11, color: _Ui.ink))),
                                                    ],
                                                  ),
                                                ),
                                            ],
                                            if (variant.durationMinutes != null && variant.durationMinutes! > 0)
                                              Padding(
                                                padding: const EdgeInsets.only(top: 6),
                                                child: Text('${variant.durationMinutes} min',
                                                  style: const TextStyle(fontSize: 10.5, color: _Ui.sub)),
                                              ),
                                          ],
                                        ),
                                      ),
                                      const SizedBox(width: 8),
                                      Text(
                                        variant.price > 0
                                            ? '₹${variant.price.toStringAsFixed(0)}'
                                            : 'Quote',
                                        style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w900, color: _Ui.violet),
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                              const SizedBox(height: 9),
                            ],
                            if (service.pricingType == 'quote' || service.bookingMode == 'inspection' || service.visitFee > 0) ...[
                              const SizedBox(height: 5),
                              Container(
                                padding: const EdgeInsets.all(13),
                                decoration: BoxDecoration(
                                  color: const Color(0xFFF7F8F6),
                                  borderRadius: BorderRadius.circular(14),
                                  border: Border.all(color: _Ui.line),
                                ),
                                child: Column(
                                  children: [
                                    _priceLine(
                                      'Service charge',
                                      servicePrice == null ? 'Confirmed after assessment' : '₹${servicePrice.toStringAsFixed(0)}',
                                    ),
                                    if (visitFee > 0) ...[
                                      const SizedBox(height: 8),
                                      _priceLine('Inspection / visit charge', '₹${visitFee.toStringAsFixed(0)}'),
                                    ],
                                    const Divider(height: 18),
                                    _priceLine(
                                      'Total before applicable taxes',
                                      total == null ? 'Confirmed after assessment' : '₹${total.toStringAsFixed(0)}',
                                      bold: true,
                                    ),
                                    if (visitFee > 0)
                                      const Padding(
                                        padding: EdgeInsets.only(top: 7),
                                        child: Text(
                                          'Visit charge is admin-configured and charged once. Any repair cost will be confirmed after assessment.',
                                          style: TextStyle(fontSize: 10.5, height: 1.35, color: _Ui.sub),
                                        ),
                                      ),
                                  ],
                                ),
                              ),
                            ],
                            const SizedBox(height: 14),
                            const Text('Add a photo (optional)', style: TextStyle(
                              fontSize: 14, fontWeight: FontWeight.w800, color: _Ui.ink,
                            )),
                            const SizedBox(height: 5),
                            const Text(
                              'Attach a photo so the professional can understand the problem.',
                              style: TextStyle(fontSize: 11.5, color: _Ui.sub),
                            ),
                            const SizedBox(height: 9),
                            if (selectedPhoto != null) ...[
                              ClipRRect(
                                borderRadius: BorderRadius.circular(12),
                                child: Image.file(selectedPhoto!, height: 150, fit: BoxFit.cover),
                              ),
                              Align(
                                alignment: Alignment.centerRight,
                                child: TextButton.icon(
                                  onPressed: () => setSheetState(() => selectedPhoto = null),
                                  icon: const Icon(Icons.delete_outline),
                                  label: const Text('Remove photo'),
                                ),
                              ),
                            ] else
                              Row(
                                children: [
                                  Expanded(
                                    child: OutlinedButton.icon(
                                      onPressed: () => pickPhoto(ImageSource.camera),
                                      icon: const Icon(Icons.camera_alt_outlined),
                                      label: const Text('Camera'),
                                    ),
                                  ),
                                  const SizedBox(width: 9),
                                  Expanded(
                                    child: OutlinedButton.icon(
                                      onPressed: () => pickPhoto(ImageSource.gallery),
                                      icon: const Icon(Icons.photo_library_outlined),
                                      label: const Text('Gallery'),
                                    ),
                                  ),
                                ],
                              ),
                            const SizedBox(height: 13),
                            const Text('Describe the actual problem (optional)', style: TextStyle(
                              fontSize: 14, fontWeight: FontWeight.w800, color: _Ui.ink,
                            )),
                            const SizedBox(height: 7),
                            TextField(
                              controller: _electricalNotesController,
                              minLines: 2,
                              maxLines: 4,
                              maxLength: 1000,
                              textCapitalization: TextCapitalization.sentences,
                              decoration: InputDecoration(
                                hintText: 'Example: The fan makes noise and stops after a few minutes...',
                                hintStyle: const TextStyle(fontSize: 11.5, color: _Ui.sub),
                                filled: true,
                                fillColor: const Color(0xFFFAFAF8),
                                border: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(13),
                                  borderSide: const BorderSide(color: _Ui.line),
                                ),
                                enabledBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(13),
                                  borderSide: const BorderSide(color: _Ui.line),
                                ),
                                contentPadding: const EdgeInsets.all(13),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 10),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton.icon(
                        onPressed: variants.isNotEmpty && selectedVariant == null
                            ? null
                            : () => Navigator.pop(
                                  sheetContext,
                                  _ElectricalAddSelection(
                                    variant: selectedVariant,
                                    notes: _electricalNotesController.text.trim(),
                                    photo: selectedPhoto,
                                  ),
                                ),
                        icon: const Icon(Icons.shopping_bag_outlined, size: 18),
                        label: const Text('Add to Cart'),
                        style: FilledButton.styleFrom(
                          backgroundColor: _Ui.violet,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 15),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(13)),
                        ),
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

    try {
      final selection = await showElectricalSheet();
      if (!mounted || selection == null) return;
      int? createdItemId;
      try {
        final cart = await BookingApi.addCartItem(
          serviceId: service.id,
          variantId: selection.variant?.id,
          quantity: 1,
          addonSelections: const [],
          formAnswers: const {},
          categoryAnswers: widget.initialAnswers,
          notes: selection.notes,
        );
        createdItemId = int.tryParse(cart['added_item_id']?.toString() ?? '');
        if (createdItemId == null) {
          throw Exception('The service was not added to the cart. Please try again.');
        }
        if (selection.photo != null) {
          await BookingApi.uploadCartItemIssuePhoto(
            itemId: createdItemId,
            photo: selection.photo!,
          );
        }
        CustomerCartState.updateFromCart(cart);
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('${service.title} added to cart'),
            action: SnackBarAction(
              label: 'VIEW CART',
              onPressed: () => Navigator.push<void>(
                context,
                MaterialPageRoute(builder: (_) => const CustomerCartScreen()),
              ),
            ),
          ),
        );
      } catch (error) {
        if (createdItemId != null) {
          try {
            await BookingApi.deleteCartItem(createdItemId);
          } catch (_) {}
        }
        rethrow;
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not add service: $error')),
        );
      }
    } finally {
      // The modal route has completed its dismissal before this method resumes.
      // Only the transparent launcher route is closed; ordinary detail pages stay open.
      if (mounted && widget.openElectricalAddOnLoad) {
        Navigator.of(context).pop();
      }
    }
  }

  Widget _priceLine(String label, String value, {bool bold = false}) => Row(
    mainAxisAlignment: MainAxisAlignment.spaceBetween,
    children: [
      Expanded(child: Text(label, style: TextStyle(
        fontSize: 12,
        color: bold ? _Ui.ink : _Ui.sub,
        fontWeight: bold ? FontWeight.w800 : FontWeight.w500,
      ))),
      const SizedBox(width: 8),
      Text(value, textAlign: TextAlign.end, style: TextStyle(
        fontSize: 12.5,
        color: _Ui.ink,
        fontWeight: bold ? FontWeight.w900 : FontWeight.w700,
      )),
    ],
  );


  List<ServiceVariant> _matchingVariants(Service service) {
    return service.variants.where((variant) {
      if (variant.attributes.isEmpty) return true;
      return variant.attributes.entries.every((entry) =>
          widget.initialAnswers[entry.key]?.toString() == entry.value.toString());
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    // This route only hosts the modal. Keep the service list visible beneath it.
    if (widget.openElectricalAddOnLoad) return const SizedBox.shrink();
    return Scaffold(
      backgroundColor: _Ui.bg,
      appBar: AppBar(
        title: Text(_service?.title ?? 'Service'),
        backgroundColor: _Ui.bg,
        actions: [
          CustomerCartBadge(
            color: _Ui.violet,
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const CustomerCartScreen()),
            ),
          ),
        ],
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
    return CustomScrollView(
      slivers: [
        _imageSliver(service),
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  service.title,
                  style: const TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.w900,
                    color: _Ui.ink,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  service.categoryName,
                  style: const TextStyle(
                    fontSize: 14,
                    color: _Ui.sub,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                if (service.description?.isNotEmpty ?? false) ...[
                  const SizedBox(height: 12),
                  Text(
                    service.description!,
                    style: const TextStyle(
                      fontSize: 14,
                      height: 1.6,
                      color: _Ui.ink,
                    ),
                  ),
                ],
                const SizedBox(height: 16),
                _infoRow(
                  Icons.access_time_rounded,
                  '${service.durationMinutes} min',
                ),
                if (service.bufferMinutes > 0)
                  _infoRow(
                    Icons.schedule_rounded,
                    '${service.bufferMinutes} min buffer',
                  ),
                if (service.visitFee > 0)
                  _infoRow(
                    Icons.local_atm_rounded,
                    'Visit fee: ₹${service.visitFee.toStringAsFixed(0)}',
                  ),
                if (service.audience != 'all')
                  _infoRow(Icons.person_rounded, service.audienceDisplay),
                if (service.bookingMode == 'inspection' || service.pricingType == 'quote')
                  Padding(
                    padding: const EdgeInsets.only(top: 14),
                    child: Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(13),
                      decoration: BoxDecoration(
                        color: const Color(0xFFFFF7E8),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: const Text(
                        'Inspection required. Any displayed visit fee is for the inspection; the final job quote will be shared after assessment.',
                        style: TextStyle(fontSize: 12, height: 1.45, color: Color(0xFF77551E)),
                      ),
                    ),
                  ),
                if (service.requiresFemaleWorker)
                  const Padding(
                    padding: EdgeInsets.only(top: 6),
                    child: Text(
                      'Female worker available on request',
                      style: TextStyle(fontSize: 12, color: _Ui.sub),
                    ),
                  ),
              ],
            ),
          ),
        ),
        if (_matchingVariants(service).isNotEmpty) ...[
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
              child: const Text(
                'Packages',
                style: TextStyle(
                  fontSize: 17,
                  fontWeight: FontWeight.w800,
                  color: _Ui.ink,
                ),
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: ListView.separated(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemCount: _matchingVariants(service).length,
              separatorBuilder: (_, _) => const SizedBox(height: 10),
              itemBuilder: (context, index) {
                final v = _matchingVariants(service)[index];
                final isElectrical = service.categoryRootSlug.toLowerCase() == 'electrical';
                return _variantCard(
                  v,
                  service.categoryName,
                  service.audience,
                  service.pricingType == 'per_unit' ? service.unitLabel : '',
                  showAdd: isElectrical,
                  onAdd: isElectrical ? () => _addElectricalService(service) : null,
                );
              },
            ),
          ),
        ],
        if (service.categoryRootSlug.toLowerCase() == 'electrical' &&
            service.pricingType == 'quote' &&
            service.visitFee > 0 &&
            _matchingVariants(service).isEmpty)
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
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
                    const Text(
                      'Professional assessment',
                      style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: _Ui.ink),
                    ),
                    const SizedBox(height: 6),
                    const Text(
                      'Add this service and describe the issue. The final repair cost will be confirmed after assessment.',
                      style: TextStyle(fontSize: 12, height: 1.4, color: _Ui.sub),
                    ),
                    const SizedBox(height: 12),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton(
                        onPressed: () => _addElectricalService(service),
                        style: FilledButton.styleFrom(backgroundColor: _Ui.violet),
                        child: const Text('ADD'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        if (service.addons.isNotEmpty) ...[
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
              child: const Text(
                'Add-ons',
                style: TextStyle(
                  fontSize: 17,
                  fontWeight: FontWeight.w800,
                  color: _Ui.ink,
                ),
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: ListView.separated(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemCount: service.addons.length,
              separatorBuilder: (_, _) => const SizedBox(height: 10),
              itemBuilder: (context, index) {
                final a = service.addons[index];
                return _addonCard(a, service.categoryName);
              },
            ),
          ),
        ],
        const SliverToBoxAdapter(child: SizedBox(height: 28)),
      ],
    );
  }

  Widget _imageSliver(Service service) {
    final imageUrls = <String>[
      if (service.image?.isNotEmpty == true) service.image!,
      ...service.images
          .map((item) => item.image)
          .where((image) => image.isNotEmpty),
    ];
    if (imageUrls.isEmpty) {
      final fallback = CatalogImageResolver.forService(
        title: service.title,
        categoryName: service.categoryName,
        audience: service.audience,
      );
      if (fallback != null) imageUrls.add(fallback);
    }
    if (imageUrls.isEmpty) {
      return SliverToBoxAdapter(
        child: Container(
          height: 190,
          color: const Color(0xFFEAF1EA),
          alignment: Alignment.center,
          child: const Icon(
            Icons.home_repair_service_rounded,
            color: Color(0xFF315C46),
            size: 52,
          ),
        ),
      );
    }
    return SliverToBoxAdapter(
      child: SizedBox(
        height: 220,
        child: PageView.builder(
          itemCount: imageUrls.length,
          itemBuilder: (context, index) => Image.network(
            imageUrls[index],
            width: double.infinity,
            fit: BoxFit.cover,
            errorBuilder: (_, __, ___) => Container(
              color: const Color(0xFFEAF1EA),
              alignment: Alignment.center,
              child: const Icon(
                Icons.broken_image_outlined,
                color: Color(0xFF987451),
                size: 42,
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _infoRow(IconData icon, String label) => Padding(
    padding: const EdgeInsets.only(top: 6),
    child: Row(
      children: [
        Icon(icon, size: 18, color: _Ui.violet),
        const SizedBox(width: 8),
        Text(label, style: const TextStyle(fontSize: 14, color: _Ui.ink)),
      ],
    ),
  );

  Widget _variantCard(
    ServiceVariant v,
    String categoryName,
    String audience,
    String unitLabel, {
    bool showAdd = false,
    VoidCallback? onAdd,
  }) {
    final variantImage = v.image?.isNotEmpty == true
        ? v.image!
        : CatalogImageResolver.forService(
              title: v.title,
              categoryName: categoryName,
              audience: audience,
            ) ??
            CatalogImageResolver.forService(
              title: categoryName,
              categoryName: categoryName,
              audience: audience,
            );
    return Container(
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(
      color: Colors.white,
      borderRadius: BorderRadius.circular(18),
      border: Border.all(color: _Ui.line),
    ),
    child: Row(
      children: [
        if (v.title.isNotEmpty)
          ClipRRect(
            borderRadius: BorderRadius.circular(10),
            child: variantImage != null
                ? Image.network(
                    variantImage,
                    width: 76,
                    height: 76,
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) => _optionImagePlaceholder(),
                  )
                : _optionImagePlaceholder(),
          )
        else
          _optionImagePlaceholder(),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                v.title,
                style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: _Ui.ink),
              ),
              if (v.description?.isNotEmpty == true)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(v.description!, style: const TextStyle(fontSize: 11, color: _Ui.sub)),
                ),
              if (v.includedTasks.isNotEmpty) ...[
                const SizedBox(height: 8),
                ...v.includedTasks.map((task) => Padding(
                  padding: const EdgeInsets.only(top: 3),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Icon(Icons.check_circle_outline, size: 14, color: _Ui.violet),
                      const SizedBox(width: 6),
                      Expanded(child: Text(task, style: const TextStyle(fontSize: 11, color: _Ui.ink))),
                    ],
                  ),
                )),
              ],
              if (v.durationMinutes != null)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text('${v.durationMinutes} min', style: const TextStyle(fontSize: 12, color: _Ui.sub)),
                ),
            ],
          ),
        ),
        const SizedBox(width: 8),
        Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (v.mrp > v.price)
              Text(
                '₹${v.mrp.toStringAsFixed(0)}',
                style: const TextStyle(fontSize: 12, decoration: TextDecoration.lineThrough, color: _Ui.sub),
              ),
            Text(
              v.price > 0
                  ? unitLabel.isNotEmpty ? '₹${v.price.toStringAsFixed(0)} / $unitLabel' : '₹${v.price.toStringAsFixed(0)}'
                  : 'Price on request',
              textAlign: TextAlign.end,
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w800, color: _Ui.violet),
            ),
            if (v.discountPercent > 0)
              Text('${v.discountPercent}% OFF', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: Color(0xFF7861A8))),
            if (showAdd) ...[
              const SizedBox(height: 8),
              SizedBox(
                height: 34,
                child: FilledButton(
                  onPressed: onAdd,
                  style: FilledButton.styleFrom(
                    backgroundColor: _Ui.violet,
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    visualDensity: VisualDensity.compact,
                  ),
                  child: const Text('ADD'),
                ),
              ),
            ],
          ],
        ),
      ],
    ),
  );
  }

  Widget _addonCard(AddOn a, String categoryName) {
    final addonImage = a.image?.isNotEmpty == true
        ? a.image!
        : CatalogImageResolver.forService(
              title: a.title,
              categoryName: categoryName,
            ) ??
            CatalogImageResolver.forService(
              title: categoryName,
              categoryName: categoryName,
            );
    return Container(
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(
      color: Colors.white,
      borderRadius: BorderRadius.circular(14),
      border: Border.all(color: _Ui.line),
    ),
    child: Row(
      children: [
        if (a.title.isNotEmpty)
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: addonImage != null
                ? Image.network(
                    addonImage,
                    width: 58,
                    height: 58,
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) =>
                        _optionImagePlaceholder(size: 58),
                  )
                : _optionImagePlaceholder(size: 58),
          )
        else
          _optionImagePlaceholder(size: 58),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                a.title,
                style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                  color: _Ui.ink,
                ),
              ),
              if (a.description?.isNotEmpty == true)
                Padding(
                  padding: const EdgeInsets.only(top: 3),
                  child: Text(a.description!, style: const TextStyle(fontSize: 11, color: _Ui.sub)),
                ),
            ],
          ),
        ),
        Text(
          a.price > 0 ? '₹${a.price.toStringAsFixed(0)}' : 'Price on request',
          textAlign: TextAlign.end,
          style: const TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w800,
            color: _Ui.violet,
          ),
        ),
      ],
    ),
  );
  }

  Widget _optionImagePlaceholder({double size = 76}) => Container(
    width: size,
    height: size,
    decoration: BoxDecoration(
      color: const Color(0xFFEAF1EA),
      borderRadius: BorderRadius.circular(10),
    ),
    alignment: Alignment.center,
    child: const Icon(Icons.photo_outlined, color: Color(0xFF748078), size: 25),
  );

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
          FilledButton(onPressed: _loadService, child: const Text('Retry')),
        ],
      ),
    ),
  );
}
