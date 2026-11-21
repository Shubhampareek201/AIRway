import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/catalog/data/catalog_api.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';
import 'package:airway/features/catalog/data/catalog_image_resolver.dart';
import 'package:airway/features/catalog/data/beauty_audience.dart';
import 'package:airway/features/catalog/presentation/service_detail_screen.dart';
import 'package:airway/features/booking/presentation/customer_cart_screen.dart';
import 'package:airway/features/booking/presentation/customer_cart_badge.dart';
import 'package:airway/features/booking/data/booking_api.dart';
import 'package:airway/core/localization/airway_text.dart';

class _PackageSelection {
  final ServiceVariant? variant;
  final String notes;
  final int quantity;
  final List<Map<String, dynamic>> addonSelections;
  final Map<String, dynamic> formAnswers;
  final File? issuePhoto;
  final Map<String, File> formPhotos;

  const _PackageSelection.add(
    this.variant,
    this.notes, {
    this.quantity = 1,
    this.addonSelections = const [],
    this.formAnswers = const {},
    this.issuePhoto,
    this.formPhotos = const {},
  });
}

/// Backend-driven service listing. Service photography uses the same canonical
/// resolver as Home and service details; admin-uploaded images take priority.
class ServiceListScreen extends StatefulWidget {
  final int categoryId;
  final String? categoryTitle;
  final int? addressId;
  final Map<String, dynamic> initialAnswers;
  final bool includeDescendants;

  const ServiceListScreen({
    super.key,
    required this.categoryId,
    this.categoryTitle,
    this.addressId,
    this.initialAnswers = const {},
    this.includeDescendants = false,
  });

  @override
  State<ServiceListScreen> createState() => _ServiceListScreenState();
}

class _ServiceListScreenState extends State<ServiceListScreen> {
  List<Service> _services = [];
  bool _loading = true;
  String? _error;
  final _searchController = TextEditingController();
  String _query = '';

  @override
  void initState() {
    super.initState();
    _loadServices();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _loadServices() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final results = await Future.wait([
        CatalogApi.listServices(
          category: widget.includeDescendants ? null : widget.categoryId,
          addressId: widget.addressId,
          audience: widget.initialAnswers['beauty_audience']?.toString(),
          categoryAnswers: widget.initialAnswers,
        ),
        CatalogApi.listCategories(
          addressId: widget.addressId,
          audience: widget.initialAnswers['beauty_audience']?.toString(),
        ),
      ]);
      var services = results[0] as List<Service>;
      final categories = results[1] as List<Category>;
      if (widget.includeDescendants) {
        final descendantIds = <int>{};
        void collect(List<Category> items) {
          for (final item in items) {
            descendantIds.add(item.id);
            collect(item.children);
          }
        }
        void findAndCollect(List<Category> items) {
          for (final item in items) {
            if (item.id == widget.categoryId) {
              descendantIds.add(item.id);
              collect(item.children);
              return;
            }
            findAndCollect(item.children);
          }
        }
        findAndCollect(categories);
        services = services
            .where((service) => descendantIds.contains(service.categoryId))
            .toList();
      }
      if (!mounted) return;
      setState(() {
        _services = services;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  List<Service> get _filteredServices {
    final lower = _query.trim().toLowerCase();
    final beautyAudience = widget.initialAnswers['beauty_audience']?.toString();
    return _services.where((service) {
      if (beautyAudience != null &&
          !BeautyAudience.includes(
            selected: beautyAudience,
            serviceAudience: service.audience,
          )) return false;
      if (lower.isEmpty) return true;
      return service.title.toLowerCase().contains(lower) ||
          service.titleHi?.toLowerCase().contains(lower) == true ||
          service.description?.toLowerCase().contains(lower) == true ||
          service.categoryName.toLowerCase().contains(lower);
    }).toList();
  }

  double _displayPrice(Service service) {
    final matchingVariants = service.variants.where((variant) {
      if (variant.attributes.isEmpty) return true;
      return variant.attributes.entries.every((entry) =>
          widget.initialAnswers[entry.key]?.toString() == entry.value.toString());
    }).toList();
    if (matchingVariants.isNotEmpty) {
      return matchingVariants.map((variant) => variant.price).reduce((a, b) => a < b ? a : b);
    }
    if (service.pricingType == "quote") return 0;
    if (service.variants.isEmpty) return 0;
    return 0;
  }

  void _openService(Service service) {
    Navigator.push<void>(
      context,
      MaterialPageRoute(
        builder: (_) => ServiceDetailScreen(
          serviceId: service.id,
          addressId: widget.addressId,
          initialAnswers: widget.initialAnswers,
        ),
      ),
    );
  }

  String _packageDescription(ServiceVariant variant) {
    final description = variant.description?.trim() ?? '';
    if (description.isNotEmpty) return description;
    final title = variant.title.toLowerCase();
    if (title.contains('basic') || title.contains('essential')) {
      return 'Essential care for everyday service needs.';
    }
    if (title.contains('standard') || title.contains('regular') || title.contains('normal')) {
      return 'A balanced option for regular upkeep and care.';
    }
    if (title.contains('premium') || title.contains('deep')) {
      return 'Enhanced care for a more detailed service experience.';
    }
    return 'A service package tailored to your selected requirements.';
  }

  Future<_PackageSelection?> _showBeautyPackageSheet(
    Service service,
    List<ServiceVariant> variants,
  ) async {
    var packageNotes = '';
    final picker = ImagePicker();
    File? selectedPhoto;
    final selectedFormPhotos = <String, File>{};
    ServiceVariant? selectedVariant;
    var quantity = 1;
    final selectedAddons = <int>{};
    final formAnswers = <String, dynamic>{};
    final fieldKeys = <String, GlobalKey>{};
    final packageSelectionKey = GlobalKey();
    final invalidFields = <String>{};
    final sheetScrollController = ScrollController();
    var validationAttempted = false;
    var variantValidationAttempted = false;

    bool isFieldMissing(CatalogFormField field) {
      if (!field.isRequired) return false;
      if (field.fieldType == 'photo') {
        return !selectedFormPhotos.containsKey(field.key);
      }
      final value = formAnswers[field.key];
      return value == null || value.toString().trim().isEmpty;
    }

    void updateFormAnswer(String fieldKey, dynamic value, StateSetter setSheetState) {
      setSheetState(() {
        if (value == null || value.toString().trim().isEmpty) {
          formAnswers.remove(fieldKey);
        } else {
          formAnswers[fieldKey] = value;
        }
        if (validationAttempted) {
          CatalogFormField? changedField;
          for (final item in service.formFields) {
            if (item.key == fieldKey) {
              changedField = item;
              break;
            }
          }
          if (changedField != null) {
            if (isFieldMissing(changedField)) {
              invalidFields.add(fieldKey);
            } else {
              invalidFields.remove(fieldKey);
            }
          }
        }
        final visibleKeys = service.formFields
            .where((field) => !widget.initialAnswers.containsKey(field.key))
            .where((field) => field.isVisibleFor({...widget.initialAnswers, ...formAnswers}))
            .map((field) => field.key)
            .toSet();
        final hiddenKeys = formAnswers.keys
            .where((key) => !visibleKeys.contains(key))
            .toList();
        for (final hiddenKey in hiddenKeys) {
          formAnswers.remove(hiddenKey);
          invalidFields.remove(hiddenKey);
          selectedFormPhotos.remove(hiddenKey);
        }
      });
    }

    try {
      return await showModalBottomSheet<_PackageSelection>(
        context: context,
        isScrollControlled: true,
        backgroundColor: Colors.transparent,
        builder: (sheetContext) => StatefulBuilder(
          builder: (context, setSheetState) {
            final visibleFields = service.formFields
                .where((field) => !widget.initialAnswers.containsKey(field.key))
                .where((field) => field.isVisibleFor({...widget.initialAnswers, ...formAnswers}))
                .toList();
            final basePrice = selectedVariant?.price ?? 0.0;
            final addonsTotal = service.addons
                .where((addon) => selectedAddons.contains(addon.id))
                .fold<double>(0, (sum, addon) => sum + addon.price);
            final visitFee = service.bookingMode == 'inspection' ? service.visitFee : 0.0;
            final estimatedSubtotal = ((basePrice + addonsTotal) * quantity) + visitFee;
            final estimatedTax = estimatedSubtotal * 0.18;
            final estimatedTotal = estimatedSubtotal + estimatedTax;

            Widget buildFormField(CatalogFormField field) {
              final current = formAnswers[field.key]?.toString() ?? '';
              if (field.fieldType == 'select') {
                final options = field.options.map((option) {
                  if (option is Map) {
                    return {
                      'label': (option['label'] ?? option['value'] ?? '').toString(),
                      'value': (option['value'] ?? option['label'] ?? '').toString(),
                    };
                  }
                  return {'label': option.toString(), 'value': option.toString()};
                }).where((option) => option['value']!.isNotEmpty).toList();
                return Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: DropdownButtonFormField<String>(
                    key: fieldKeys.putIfAbsent(field.key, () => GlobalKey()),
                    value: options.any((option) => option['value'] == current)
                        ? current
                        : null,
                    decoration: InputDecoration(
                      labelText: field.isRequired ? '${field.displayLabel} *' : field.displayLabel,
                      errorText: invalidFields.contains(field.key)
                          ? 'Please select ${field.displayLabel.toLowerCase()}'
                          : null,
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                    ),
                    items: options.map((option) => DropdownMenuItem<String>(
                      value: option['value'],
                      child: Text(option['label']!),
                    )).toList(),
                    onChanged: (value) => updateFormAnswer(field.key, value, setSheetState),
                  ),
                );
              }
              if (field.fieldType == 'photo') {
                final photo = selectedFormPhotos[field.key];
                return Padding(
                  key: fieldKeys.putIfAbsent(field.key, () => GlobalKey()),
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        field.isRequired ? '${field.displayLabel} *' : field.displayLabel,
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                          color: invalidFields.contains(field.key) ? Colors.red.shade700 : AirwayColors.text,
                        ),
                      ),
                      const SizedBox(height: 7),
                      if (photo != null) ...[
                        Container(
                          decoration: BoxDecoration(
                            border: Border.all(
                              color: invalidFields.contains(field.key) ? Colors.red.shade600 : Colors.transparent,
                              width: invalidFields.contains(field.key) ? 1.4 : 0,
                            ),
                            borderRadius: BorderRadius.circular(13),
                          ),
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(12),
                            child: Container(
                              height: 150,
                              width: double.infinity,
                              color: AirwayColors.surfaceVariant,
                              alignment: Alignment.center,
                              child: Image.file(
                                photo,
                                height: 150,
                                width: double.infinity,
                                fit: BoxFit.contain,
                              ),
                            ),
                          ),
                        ),
                        Align(
                          alignment: Alignment.centerRight,
                          child: TextButton.icon(
                            onPressed: () {
                              selectedFormPhotos.remove(field.key);
                              updateFormAnswer(field.key, null, setSheetState);
                            },
                            icon: const Icon(Icons.delete_outline),
                            label: Text(AirwayText.tr('Remove photo', 'फ़ोटो हटाएँ')),
                          ),
                        ),
                      ] else
                        Container(
                          padding: const EdgeInsets.all(5),
                          decoration: BoxDecoration(
                            border: Border.all(
                              color: invalidFields.contains(field.key)
                                  ? Colors.red.shade600
                                  : Colors.transparent,
                              width: invalidFields.contains(field.key) ? 1.2 : 0,
                            ),
                            borderRadius: BorderRadius.circular(13),
                          ),
                          child: Row(children: [
                          Expanded(child: OutlinedButton.icon(
                            onPressed: () async {
                              final picked = await picker.pickImage(
                                source: ImageSource.camera, imageQuality: 82,
                                maxWidth: 1600, maxHeight: 1600,
                              );
                              if (picked != null && sheetContext.mounted) {
                                selectedFormPhotos[field.key] = File(picked.path);
                                updateFormAnswer(field.key, null, setSheetState);
                              }
                            },
                            icon: const Icon(Icons.camera_alt_outlined),
                            label: Text(AirwayText.tr('Camera', 'कैमरा')),
                          )),
                          const SizedBox(width: 8),
                          Expanded(child: OutlinedButton.icon(
                            onPressed: () async {
                              final picked = await picker.pickImage(
                                source: ImageSource.gallery, imageQuality: 82,
                                maxWidth: 1600, maxHeight: 1600,
                              );
                              if (picked != null && sheetContext.mounted) {
                                selectedFormPhotos[field.key] = File(picked.path);
                                updateFormAnswer(field.key, null, setSheetState);
                              }
                            },
                            icon: const Icon(Icons.photo_library_outlined),
                            label: Text(AirwayText.tr('Gallery', 'गैलरी')),
                          )),
                          ]),
                        ),
                      if (invalidFields.contains(field.key))
                        const Padding(
                          padding: EdgeInsets.only(top: 5),
                          child: Text(
                            'Please upload this required photo.',
                            style: TextStyle(color: Colors.red, fontSize: 12),
                          ),
                        ),
                    ],
                  ),
                );
              }
              return Padding(
                key: fieldKeys.putIfAbsent(field.key, () => GlobalKey()),
                padding: const EdgeInsets.only(bottom: 12),
                child: TextFormField(
                  key: ValueKey(field.key),
                  initialValue: current,
                  keyboardType: field.fieldType == 'number'
                      ? const TextInputType.numberWithOptions(decimal: true)
                      : TextInputType.text,
                  minLines: field.fieldType == 'textarea' ? 2 : 1,
                  maxLines: field.fieldType == 'textarea' ? 4 : 1,
                  readOnly: field.fieldType == 'date',
                  onTap: field.fieldType == 'date'
                      ? () async {
                          final picked = await showDatePicker(
                            context: sheetContext,
                            initialDate: DateTime.now(),
                            firstDate: DateTime.now(),
                            lastDate: DateTime.now().add(const Duration(days: 3650)),
                          );
                          if (picked != null && sheetContext.mounted) {
                            final value = '${picked.year.toString().padLeft(4, '0')}-'
                                '${picked.month.toString().padLeft(2, '0')}-'
                                '${picked.day.toString().padLeft(2, '0')}';
                            updateFormAnswer(field.key, value, setSheetState);
                          }
                        }
                      : null,
                  onChanged: (value) => updateFormAnswer(field.key, value.trim(), setSheetState),
                  decoration: InputDecoration(
                    labelText: field.isRequired ? '${field.displayLabel} *' : field.displayLabel,
                    hintText: field.fieldType == 'date' ? 'Select date' : null,
                    errorText: invalidFields.contains(field.key)
                        ? 'Please enter ${field.displayLabel.toLowerCase()}'
                        : null,
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                ),
              );
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
                    Center(child: Container(
                      width: 40, height: 4,
                      decoration: BoxDecoration(
                        color: AirwayColors.border,
                        borderRadius: BorderRadius.circular(8),
                      ),
                    )),
                    const SizedBox(height: 16),
                    Row(children: [
                      Expanded(child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(service.displayTitle, style: const TextStyle(
                            fontSize: 19, fontWeight: FontWeight.w900,
                            color: AirwayColors.text,
                          )),
                          const SizedBox(height: 4),
                          Text(
                            service.pricingType == 'per_unit'
                                ? 'Choose quantity, package and optional extras'
                                : 'Choose the package and service details',
                            style: const TextStyle(fontSize: 12, color: AirwayColors.textSecondary),
                          ),
                        ],
                      )),
                      const Icon(Icons.auto_awesome_rounded, color: AirwayColors.primary, size: 25),
                    ]),
                    const SizedBox(height: 14),
                    Flexible(child: SingleChildScrollView(
                      controller: sheetScrollController,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          if (variants.isEmpty)
                            Container(
                              width: double.infinity,
                              padding: const EdgeInsets.all(14),
                              decoration: BoxDecoration(
                                color: AirwayColors.primarySoft,
                                borderRadius: BorderRadius.circular(14),
                              ),
                              child: Text(
                                service.pricingType == 'quote'
                                    ? 'The professional will confirm the final service cost after assessment.'
                                    : 'This service will be added at its listed price.',
                                style: const TextStyle(fontSize: 12, height: 1.4, color: AirwayColors.text),
                              ),
                            ),
                          if (variantValidationAttempted)
                            const Padding(
                              padding: EdgeInsets.only(bottom: 8),
                              child: Text(
                                'Please select a package to continue.',
                                style: TextStyle(color: Colors.red, fontSize: 12, fontWeight: FontWeight.w600),
                              ),
                            ),
                          for (final variant in variants) ...[
                            KeyedSubtree(
                              key: variant == variants.first ? packageSelectionKey : null,
                              child: _buildPackageOption(
                                variant,
                                selected: selectedVariant?.id == variant.id,
                                description: _packageDescription(variant),
                                onTap: () => setSheetState(() {
                                  selectedVariant = variant;
                                  variantValidationAttempted = false;
                                }),
                              ),
                            ),
                            const SizedBox(height: 9),
                          ],
                          if (service.pricingType == 'per_unit') ...[
                            const SizedBox(height: 8),
                            Row(children: [
                              Expanded(child: Text(
                                'Quantity (${service.unitLabel.isEmpty ? 'units' : service.unitLabel})',
                                style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w800, color: AirwayColors.text),
                              )),
                              IconButton(
                                onPressed: quantity > 1 ? () => setSheetState(() => quantity--) : null,
                                icon: const Icon(Icons.remove_circle_outline),
                              ),
                              Text('$quantity', style: const TextStyle(fontWeight: FontWeight.w900)),
                              IconButton(
                                onPressed: quantity < 10000 ? () => setSheetState(() => quantity++) : null,
                                icon: const Icon(Icons.add_circle_outline),
                              ),
                            ]),
                          ],
                          if (service.addons.isNotEmpty) ...[
                            const SizedBox(height: 12),
                            Text(AirwayText.tr('Optional add-ons', 'वैकल्पिक अतिरिक्त सेवाएँ'), style: TextStyle(
                              fontSize: 14, fontWeight: FontWeight.w800, color: AirwayColors.text,
                            )),
                            const SizedBox(height: 7),
                            for (final addon in service.addons) ...[
                              CheckboxListTile(
                                contentPadding: EdgeInsets.zero,
                                dense: true,
                                controlAffinity: ListTileControlAffinity.leading,
                                value: selectedAddons.contains(addon.id),
                                onChanged: (checked) => setSheetState(() {
                                  if (checked == true) {
                                    selectedAddons.add(addon.id);
                                  } else {
                                    selectedAddons.remove(addon.id);
                                  }
                                }),
                                title: Text(addon.displayTitle, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700)),
                                subtitle: addon.description?.isNotEmpty == true
                                    ? Text(addon.description!, style: const TextStyle(fontSize: 11))
                                    : null,
                                secondary: Text('₹${addon.price.toStringAsFixed(0)}',
                                  style: const TextStyle(fontWeight: FontWeight.w800, color: AirwayColors.primary)),
                              ),
                            ],
                          ],
                          if (visibleFields.isNotEmpty) ...[
                            const SizedBox(height: 12),
                            Text(AirwayText.tr('A few service details', 'सेवा से जुड़ी कुछ जानकारी'), style: TextStyle(
                              fontSize: 14, fontWeight: FontWeight.w800, color: AirwayColors.text,
                            )),
                            const SizedBox(height: 8),
                            for (final field in visibleFields) buildFormField(field),
                          ],
                          const SizedBox(height: 5),
                          Align(
                            alignment: Alignment.centerLeft,
                            child: Text(AirwayText.tr('Anything we should know?', 'क्या हमें कुछ और जानना चाहिए?'),
                              style: TextStyle(fontSize: 14, fontWeight: FontWeight.w800, color: AirwayColors.text)),
                          ),
                          const SizedBox(height: 7),
                          TextField(
                            onChanged: (value) => packageNotes = value,
                            minLines: 2,
                            maxLines: 4,
                            maxLength: 1000,
                            textCapitalization: TextCapitalization.sentences,
                            decoration: InputDecoration(
                              hintText: AirwayText.tr('Add a request or special instruction (optional)', 'कोई अनुरोध या विशेष निर्देश लिखें (वैकल्पिक)'),
                              hintStyle: const TextStyle(fontSize: 12, color: AirwayColors.textSecondary),
                              filled: true,
                              fillColor: AirwayColors.background,
                              border: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(13),
                                borderSide: const BorderSide(color: AirwayColors.border),
                              ),
                              enabledBorder: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(13),
                                borderSide: const BorderSide(color: AirwayColors.border),
                              ),
                              contentPadding: const EdgeInsets.all(13),
                            ),
                          ),
                          if (service.categoryRootSlug.toLowerCase() == 'electrical') ...[
                            const SizedBox(height: 12),
                            Text(AirwayText.tr('Issue photo (optional)', 'समस्या की फ़ोटो (वैकल्पिक)'), style: TextStyle(
                              fontSize: 14, fontWeight: FontWeight.w800, color: AirwayColors.text,
                            )),
                            const SizedBox(height: 7),
                            if (selectedPhoto != null) ...[
                              ClipRRect(
                                borderRadius: BorderRadius.circular(12),
                                child: Image.file(selectedPhoto!, height: 140, width: double.infinity, fit: BoxFit.cover),
                              ),
                              Align(
                                alignment: Alignment.centerRight,
                                child: TextButton.icon(
                                  onPressed: () => setSheetState(() => selectedPhoto = null),
                                  icon: const Icon(Icons.delete_outline),
                                  label: Text(AirwayText.tr('Remove photo', 'फ़ोटो हटाएँ')),
                                ),
                              ),
                            ] else
                              Row(children: [
                                Expanded(child: OutlinedButton.icon(
                                  onPressed: () async {
                                    final picked = await picker.pickImage(
                                      source: ImageSource.camera, imageQuality: 82,
                                      maxWidth: 1600, maxHeight: 1600,
                                    );
                                    if (picked != null) setSheetState(() => selectedPhoto = File(picked.path));
                                  },
                                  icon: const Icon(Icons.camera_alt_outlined),
                                  label: Text(AirwayText.tr('Camera', 'कैमरा')),
                                )),
                                const SizedBox(width: 8),
                                Expanded(child: OutlinedButton.icon(
                                  onPressed: () async {
                                    final picked = await picker.pickImage(
                                      source: ImageSource.gallery, imageQuality: 82,
                                      maxWidth: 1600, maxHeight: 1600,
                                    );
                                    if (picked != null) setSheetState(() => selectedPhoto = File(picked.path));
                                  },
                                  icon: const Icon(Icons.photo_library_outlined),
                                  label: Text(AirwayText.tr('Gallery', 'गैलरी')),
                                )),
                              ]),
                          ],
                          if (service.bookingMode == 'inspection' && service.visitFee > 0) ...[
                            const SizedBox(height: 10),
                            Text(AirwayText.tr('Inspection / visit charge: ₹${service.visitFee.toStringAsFixed(0)} (charged once)', 'निरीक्षण / विज़िट शुल्क: ₹${service.visitFee.toStringAsFixed(0)} (एक बार लिया जाएगा)'),
                              style: const TextStyle(fontSize: 12, color: AirwayColors.textSecondary)),
                          ],
                        ],
                      ),
                    )),
                    const SizedBox(height: 8),
                    if (service.pricingType != 'quote')
                      Align(
                        alignment: Alignment.centerRight,
                        child: Text(
                          'Estimated total incl. GST: ₹${estimatedTotal.toStringAsFixed(0)}',
                          style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w900, color: AirwayColors.primary),
                        ),
                      ),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton.icon(
                        onPressed: () {
                                final missingFields = visibleFields
                                    .where(isFieldMissing)
                                    .toList();
                                final missingVariant = variants.isNotEmpty && selectedVariant == null;
                                if (missingFields.isNotEmpty || missingVariant) {
                                  setSheetState(() {
                                    validationAttempted = true;
                                    variantValidationAttempted = missingVariant;
                                    invalidFields
                                      ..clear()
                                      ..addAll(missingFields.map((field) => field.key));
                                  });
                                  final firstKey = missingVariant
                                      ? packageSelectionKey
                                      : fieldKeys[missingFields.first.key];
                                  WidgetsBinding.instance.addPostFrameCallback((_) {
                                    final targetContext = firstKey?.currentContext;
                                    if (targetContext != null && sheetScrollController.hasClients) {
                                      Scrollable.ensureVisible(
                                        targetContext,
                                        alignment: 0.18,
                                        duration: const Duration(milliseconds: 280),
                                        curve: Curves.easeOutCubic,
                                      );
                                    }
                                  });
                                  return;
                                }
                                Navigator.pop(
                                  sheetContext,
                                  _PackageSelection.add(
                                    selectedVariant,
                                    packageNotes.trim(),
                                    quantity: quantity,
                                    addonSelections: selectedAddons.map((id) => {'id': id, 'quantity': 1}).toList(),
                                    formAnswers: Map<String, dynamic>.from(formAnswers),
                                    issuePhoto: selectedPhoto,
                                    formPhotos: Map<String, File>.from(selectedFormPhotos),
                                  ),
                                );
                              },
                        icon: const Icon(Icons.shopping_bag_outlined, size: 18),
                        label: Text(AirwayText.tr('Add to Cart', 'कार्ट में जोड़ें')),
                        style: FilledButton.styleFrom(
                          backgroundColor: AirwayColors.primary,
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
    } finally {
      // The modal route has completed before this method resumes.
      // Dispose only the scroll controller; form fields own their internal state.
      sheetScrollController.dispose();
    }
  }

  Widget _buildPackageOption(
    ServiceVariant variant, {
    required bool selected,
    required String description,
    required VoidCallback onTap,
  }) {
    return Material(
      color: selected ? AirwayColors.primarySoft : Colors.white,
      borderRadius: BorderRadius.circular(15),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(15),
        child: Container(
          padding: const EdgeInsets.all(13),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(15),
            border: Border.all(
              color: selected ? AirwayColors.primary : AirwayColors.border,
              width: selected ? 1.7 : 1,
            ),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(
                selected ? Icons.radio_button_checked_rounded : Icons.radio_button_off_rounded,
                color: AirwayColors.primary,
                size: 21,
              ),
              const SizedBox(width: 10),
              Expanded(child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(variant.displayTitle, style: const TextStyle(
                    fontSize: 14, fontWeight: FontWeight.w900, color: AirwayColors.text,
                  )),
                  const SizedBox(height: 4),
                  Text(description, style: const TextStyle(
                    fontSize: 11.5, height: 1.35, color: AirwayColors.textSecondary,
                  )),
                  if (variant.includedTasks.isNotEmpty) ...[
                    const SizedBox(height: 7),
                    for (final task in variant.includedTasks)
                      Padding(
                        padding: const EdgeInsets.only(top: 3),
                        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          const Icon(Icons.check_rounded, size: 14, color: AirwayColors.primary),
                          const SizedBox(width: 5),
                          Expanded(child: Text(task, style: const TextStyle(
                            fontSize: 11, color: AirwayColors.text,
                          ))),
                        ]),
                      ),
                  ],
                  if (variant.durationMinutes != null && variant.durationMinutes! > 0)
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Text('${variant.durationMinutes} min',
                        style: const TextStyle(fontSize: 10.5, color: AirwayColors.textSecondary)),
                    ),
                ],
              )),
              const SizedBox(width: 8),
              Text('₹${variant.price.toStringAsFixed(0)}', style: const TextStyle(
                fontSize: 15, fontWeight: FontWeight.w900, color: AirwayColors.primary,
              )),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _startAddFlow(Service service) async {
    // Every category uses one Admin-driven add popup. Electrical adds its
    // optional issue photo and inspection context inside the same experience.
    // Scheduling and address selection remain in shared checkout.

    final availableVariants = service.variants.where((variant) {
      if (variant.attributes.isEmpty) return true;
      return variant.attributes.entries.every((entry) =>
          widget.initialAnswers[entry.key]?.toString() == entry.value.toString());
    }).toList();
    if (service.variants.isNotEmpty && availableVariants.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('No package is available for this selection.', 'इस चयन के लिए कोई पैकेज उपलब्ध नहीं है।'))),
      );
      return;
    }

    final selection = await _showBeautyPackageSheet(service, availableVariants);
    if (!mounted || selection == null) return;
    try {
      final updatedCart = await BookingApi.addCartItem(
        serviceId: service.id,
        variantId: selection.variant?.id,
        quantity: selection.quantity,
        addonSelections: selection.addonSelections,
        formAnswers: selection.formAnswers,
        categoryAnswers: widget.initialAnswers,
        notes: selection.notes,
      );
      final addedItemId = int.tryParse(updatedCart['added_item_id']?.toString() ?? '');
      if (selection.issuePhoto != null || selection.formPhotos.isNotEmpty) {
        if (addedItemId == null) {
          throw Exception('The service was added but its photos could not be attached.');
        }
        try {
          if (selection.issuePhoto != null) {
            await BookingApi.uploadCartItemIssuePhoto(
              itemId: addedItemId,
              photo: selection.issuePhoto!,
            );
          }
          for (final entry in selection.formPhotos.entries) {
            await BookingApi.uploadCartItemFormPhoto(
              itemId: addedItemId,
              fieldKey: entry.key,
              photo: entry.value,
            );
          }
        } catch (_) {
          try {
            await BookingApi.deleteCartItem(addedItemId);
          } catch (_) {}
          rethrow;
        }
      }
      final latestCart = selection.issuePhoto == null && selection.formPhotos.isEmpty
          ? updatedCart
          : await BookingApi.getCart();
      CustomerCartState.updateFromCart(latestCart);
      if (!mounted) return;
      ScaffoldMessenger.of(context).hideCurrentSnackBar();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          behavior: SnackBarBehavior.floating,
          backgroundColor: Colors.transparent,
          elevation: 0,
          padding: EdgeInsets.zero,
          margin: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          duration: const Duration(seconds: 3),
          content: Container(
            padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 13),
            decoration: BoxDecoration(
              color: const Color(0xFF18352A),
              borderRadius: BorderRadius.circular(17),
              border: Border.all(color: AirwayColors.primary.withOpacity(0.45)),
              boxShadow: const [
                BoxShadow(color: Color(0x26000000), blurRadius: 18, offset: Offset(0, 7)),
              ],
            ),
            child: Row(
              children: [
                Container(
                  width: 34,
                  height: 34,
                  decoration: BoxDecoration(
                    color: AirwayColors.primary.withOpacity(0.20),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(Icons.check_rounded, color: Colors.white, size: 21),
                ),
                const SizedBox(width: 11),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(AirwayText.tr('Added to cart', 'कार्ट में जोड़ दिया गया'), style: TextStyle(
                        color: Colors.white, fontSize: 13, fontWeight: FontWeight.w800,
                      )),
                      Text(service.displayTitle, maxLines: 1, overflow: TextOverflow.ellipsis,
                        style: const TextStyle(color: Color(0xFFDCE8DF), fontSize: 11)),
                    ],
                  ),
                ),
                TextButton(
                  onPressed: () {
                    ScaffoldMessenger.of(context).hideCurrentSnackBar();
                    Navigator.push<void>(
                      context,
                      MaterialPageRoute(builder: (_) => const CustomerCartScreen()),
                    );
                  },
                  style: TextButton.styleFrom(
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 7),
                    minimumSize: Size.zero,
                  ),
                  child: Text(AirwayText.tr('VIEW CART', 'कार्ट देखें'), style: TextStyle(
                    fontSize: 10, fontWeight: FontWeight.w900, letterSpacing: 0.3,
                  )),
                ),
              ],
            ),
          ),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Could not add service: $e', 'सेवा कार्ट में नहीं जुड़ सकी: $e'))),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final title = widget.categoryTitle ?? 'Services';
    return Scaffold(
      backgroundColor: AirwayColors.background,
      appBar: AppBar(
        title: Text(title),
        backgroundColor: AirwayColors.background,
        actions: [
          CustomerCartBadge(
            onTap: () => Navigator.push<void>(
              context,
              MaterialPageRoute(builder: (_) => const CustomerCartScreen()),
            ),
          ),
        ],
      ),
      body: Column(
        children: [
          _searchBar(),
          Expanded(
            child: _loading
                ? const Center(
                    child: CircularProgressIndicator(color: AirwayColors.primary),
                  )
                : _error != null
                    ? _errorWidget(_error!)
                    : _filteredServices.isEmpty
                        ? _emptyState()
                        : _buildList(),
          ),
        ],
      ),
    );
  }

  Widget _searchBar() => Padding(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 12),
        child: TextField(
          controller: _searchController,
          textInputAction: TextInputAction.search,
          onChanged: (value) => setState(() => _query = value),
          decoration: InputDecoration(
            hintText: AirwayText.tr('Search ${widget.categoryTitle ?? "services"}...', '${widget.categoryTitle ?? "सेवाएँ"} खोजें...'),
            hintStyle: const TextStyle(
              fontSize: 13.5,
              color: AirwayColors.textSecondary,
            ),
            prefixIcon: const Icon(Icons.search_rounded, color: AirwayColors.primary),
            suffixIcon: _query.isNotEmpty
                ? IconButton(
                    tooltip: AirwayText.tr('Clear search', 'खोज हटाएँ'),
                    onPressed: () {
                      _searchController.clear();
                      setState(() => _query = '');
                    },
                    icon: const Icon(Icons.close_rounded, size: 19),
                  )
                : null,
            filled: true,
            fillColor: AirwayColors.surface,
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(17),
              borderSide: BorderSide.none,
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(17),
              borderSide: BorderSide.none,
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(17),
              borderSide: const BorderSide(color: AirwayColors.primary, width: 1.5),
            ),
            contentPadding: const EdgeInsets.symmetric(vertical: 15),
          ),
        ),
      );

  Widget _buildList() {
    final services = _filteredServices;
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 28),
      children: [
        Container(
          width: double.infinity,
          margin: const EdgeInsets.only(bottom: 14),
          padding: const EdgeInsets.all(17),
          decoration: BoxDecoration(
            color: AirwayColors.primarySoft,
            borderRadius: BorderRadius.circular(16),
          ),
          child: Row(
            children: [
              const Icon(Icons.home_repair_service_rounded, color: AirwayColors.primary, size: 34),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _audienceTitle,
                      style: const TextStyle(
                        color: AirwayColors.text,
                        fontSize: 18,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                    const SizedBox(height: 3),
                    const Text(
                      'Choose the service you need',
                      style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(2, 2, 2, 10),
          child: Text(
            'Services (${services.length})',
            style: const TextStyle(
              color: AirwayColors.text,
              fontSize: 17,
              fontWeight: FontWeight.w900,
            ),
          ),
        ),
        for (final service in services) ...[
          _serviceCard(service),
          const SizedBox(height: 11),
        ],
      ],
    );
  }

  String get _audienceTitle {
    final category = widget.categoryTitle ?? 'Services';
    switch (widget.initialAnswers['beauty_audience']?.toString()) {
      case BeautyAudience.men:
        return "Men's $category";
      case BeautyAudience.women:
        return "Women's $category";
      case BeautyAudience.both:
        return "Unisex $category";
      default:
        return category;
    }
  }

  Widget _serviceImage(Service service) {
    final imageUrl = (service.image?.isNotEmpty == true)
        ? service.image!
        : service.images.isNotEmpty
            ? service.images.first.image
            : CatalogImageResolver.forService(
                title: service.displayTitle,
                categoryName: service.categoryName,
                audience: service.audience,
              );
    return ClipRRect(
      borderRadius: BorderRadius.circular(11),
      child: SizedBox(
        width: 76,
        height: 76,
        child: imageUrl == null || imageUrl.isEmpty
            ? Container(
                color: AirwayColors.primarySoft,
                alignment: Alignment.center,
                child: const Icon(
                  Icons.home_repair_service_rounded,
                  color: AirwayColors.primary,
                  size: 30,
                ),
              )
            : Image.network(
                imageUrl,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => Container(
                  color: AirwayColors.primarySoft,
                  alignment: Alignment.center,
                  child: const Icon(
                    Icons.broken_image_outlined,
                    color: AirwayColors.primary,
                    size: 28,
                  ),
                ),
              ),
      ),
    );
  }

  Widget _serviceCard(Service service) {
    final price = _displayPrice(service);
    final description = service.description?.trim() ?? '';
    return Material(
      color: AirwayColors.surface,
      borderRadius: BorderRadius.circular(15),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: service.isAvailable ? () => _openService(service) : null,
        child: Container(
          padding: const EdgeInsets.all(11),
          decoration: BoxDecoration(
            border: Border.all(color: AirwayColors.border),
            borderRadius: BorderRadius.circular(15),
          ),
          child: Row(
            children: [
              _serviceImage(service),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      service.displayTitle,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: AirwayColors.text,
                        fontSize: 14,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    if (description.isNotEmpty) ...[
                      const SizedBox(height: 4),
                      Text(
                        description,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: AirwayColors.textSecondary,
                          fontSize: 11,
                          height: 1.3,
                        ),
                      ),
                    ],
                    const SizedBox(height: 5),
                    Text(
                      service.durationMinutes > 0
                          ? '${service.durationMinutes} min'
                          : service.categoryName,
                      style: const TextStyle(
                        color: AirwayColors.textSecondary,
                        fontSize: 10.5,
                      ),
                    ),
                    const SizedBox(height: 5),
                    Text(
                      service.pricingType == 'quote'
                          ? (service.visitFee > 0 ? 'Visit fee ₹${service.visitFee.toStringAsFixed(0)}' : 'Inspection & quote')
                          : price > 0
                              ? service.pricingType == 'per_unit' && service.unitLabel.isNotEmpty
                                  ? 'From ₹${price.toStringAsFixed(0)} / ${service.unitLabel}'
                                  : 'From ₹${price.toStringAsFixed(0)}'
                              : 'Price on request',
                      style: const TextStyle(
                        color: AirwayColors.text,
                        fontSize: 13,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              OutlinedButton(
                onPressed: service.isAvailable ? () => _startAddFlow(service) : null,
                style: OutlinedButton.styleFrom(
                  foregroundColor: AirwayColors.primary,
                  side: const BorderSide(color: AirwayColors.primary),
                  padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 9),
                  minimumSize: Size.zero,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(9)),
                ),
                child: Text(
                  service.isAvailable ? 'ADD' : 'UNAVAILABLE',
                  style: TextStyle(fontSize: 11, fontWeight: FontWeight.w900),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _emptyState() => Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.design_services_outlined, size: 64, color: AirwayColors.textSecondary),
              const SizedBox(height: 20),
              const Text(
                'No services available',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: AirwayColors.text),
              ),
              const SizedBox(height: 8),
              const Text(
                'Services in this category will appear here once they are added.',
                style: TextStyle(color: AirwayColors.textSecondary),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 20),
              FilledButton(onPressed: _loadServices, child: Text(AirwayText.tr('Retry', 'फिर कोशिश करें'))),
            ],
          ),
        ),
      );

  Widget _errorWidget(String message) => Center(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, color: Colors.redAccent, size: 52),
              const SizedBox(height: 14),
              Text(message, textAlign: TextAlign.center, style: const TextStyle(color: AirwayColors.textSecondary)),
              const SizedBox(height: 20),
              FilledButton(onPressed: _loadServices, child: Text(AirwayText.tr('Retry', 'फिर कोशिश करें'))),
            ],
          ),
        ),
      );
}
