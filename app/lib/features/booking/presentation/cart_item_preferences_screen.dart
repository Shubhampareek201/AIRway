import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:airway/features/catalog/data/catalog_api.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';
import 'package:airway/features/booking/data/booking_api.dart';

class CartItemPreferencesScreen extends StatefulWidget {
  final int cartItemId;
  final int serviceId;
  final String serviceTitle;
  final Map<String, dynamic> categoryAnswers;
  final Map<String, dynamic> initialAnswers;
  final String initialNotes;
  final bool hasIssuePhoto;

  const CartItemPreferencesScreen({
    super.key,
    required this.cartItemId,
    required this.serviceId,
    required this.serviceTitle,
    required this.categoryAnswers,
    required this.initialAnswers,
    this.initialNotes = '',
    this.hasIssuePhoto = false,
  });

  @override
  State<CartItemPreferencesScreen> createState() => _CartItemPreferencesScreenState();
}

class _CartItemPreferencesScreenState extends State<CartItemPreferencesScreen> {
  static const green = Color(0xFF315C46);
  static const ink = Color(0xFF1E2923);
  static const muted = Color(0xFF748078);
  static const line = Color(0xFFEAE6DE);

  Service? service;
  bool loading = true;
  bool saving = false;
  String? error;
  final Map<String, dynamic> answers = {};
  final Map<String, dynamic> categoryAnswers = {};
  final Map<String, TextEditingController> controllers = {};
  final TextEditingController notesController = TextEditingController();
  final ImagePicker picker = ImagePicker();
  File? selectedPhoto;
  bool removeExistingPhoto = false;
  final Map<String, File> selectedFormPhotos = {};
  final Set<String> removedFormPhotos = {};

  @override
  void initState() {
    super.initState();
    answers.addAll(widget.initialAnswers);
    notesController.text = widget.initialNotes;
    categoryAnswers.addAll(widget.categoryAnswers);
    _load();
  }

  @override
  void dispose() {
    for (final controller in controllers.values) {
      controller.dispose();
    }
    notesController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final value = await CatalogApi.getService(
        widget.serviceId,
        categoryAnswers: categoryAnswers,
      );
      if (!mounted) return;
      setState(() {
        service = value;
        loading = false;
      });
    } catch (e) {
      if (mounted) setState(() { error = e.toString(); loading = false; });
    }
  }

  List<CatalogFormField> get visibleFields {
    final combined = <String, dynamic>{...categoryAnswers, ...answers};
    return (service?.formFields ?? const <CatalogFormField>[])
        .where((field) => !categoryAnswers.containsKey(field.key))
        .where((field) => field.isVisibleFor(combined))
        .toList();
  }

  void _setAnswer(String key, dynamic value) {
    setState(() {
      answers[key] = value;
      var changed = true;
      while (changed) {
        changed = false;
        final visible = visibleFields.map((field) => field.key).toSet();
        final stale = answers.keys.where((key) => !visible.contains(key)).toList();
        if (stale.isNotEmpty) {
          for (final key in stale) {
            answers.remove(key);
            selectedFormPhotos.remove(key);
            controllers.remove(key)?.dispose();
          }
          changed = true;
        }
      }
    });
  }

  Future<void> _pickFormPhoto(String fieldKey, ImageSource source) async {
    try {
      final picked = await picker.pickImage(
        source: source,
        imageQuality: 82,
        maxWidth: 1600,
        maxHeight: 1600,
      );
      if (picked != null && mounted) {
        setState(() {
          selectedFormPhotos[fieldKey] = File(picked.path);
          removedFormPhotos.remove(fieldKey);
          answers[fieldKey] = 'uploaded';
        });
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not select photo: $e')),
        );
      }
    }
  }

  Future<void> _pickIssuePhoto(ImageSource source) async {
    try {
      final picked = await picker.pickImage(
        source: source,
        imageQuality: 82,
        maxWidth: 1600,
        maxHeight: 1600,
      );
      if (picked != null && mounted) {
        setState(() {
          selectedPhoto = File(picked.path);
          removeExistingPhoto = false;
        });
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not select photo: $e')),
        );
      }
    }
  }

  Future<void> _save() async {
    for (final field in visibleFields) {
      final value = answers[field.key];
      final hasSelectedPhoto = selectedFormPhotos.containsKey(field.key);
      if (field.fieldType == 'photo' && field.isRequired &&
          !hasSelectedPhoto && value?.toString() != 'uploaded') {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Please upload: ${field.label}')),
        );
        return;
      }
      if (field.fieldType != 'photo' && field.isRequired &&
          (value == null || value.toString().trim().isEmpty)) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Please complete: ${field.label}')),
        );
        return;
      }
    }
    final visibleKeys = visibleFields.map((field) => field.key).toSet();
    final visibleAnswers = Map<String, dynamic>.fromEntries(
      answers.entries.where((entry) => visibleKeys.contains(entry.key)),
    );
    setState(() => saving = true);
    try {
      // Upload replacements first so required photo fields already have valid
      // server-side metadata when the cart answers are validated.
      for (final entry in selectedFormPhotos.entries) {
        await BookingApi.uploadCartItemFormPhoto(
          itemId: widget.cartItemId,
          fieldKey: entry.key,
          photo: entry.value,
        );
      }
      for (final fieldKey in removedFormPhotos) {
        if (!selectedFormPhotos.containsKey(fieldKey)) {
          await BookingApi.removeCartItemFormPhoto(widget.cartItemId, fieldKey);
        }
      }
      await BookingApi.updateCartItem(
        itemId: widget.cartItemId,
        data: {
          'form_answers': visibleAnswers,
          'category_answers': categoryAnswers,
          'notes': notesController.text.trim(),
        },
      );
      if (selectedPhoto != null) {
        await BookingApi.uploadCartItemIssuePhoto(
          itemId: widget.cartItemId,
          photo: selectedPhoto!,
        );
      } else if (removeExistingPhoto) {
        await BookingApi.removeCartItemIssuePhoto(widget.cartItemId);
      }
      if (!mounted) return;
      Navigator.pop(context, true);
    } catch (e) {
      if (mounted) {
        setState(() => saving = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not save preferences: $e')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        title: const Text('Service preferences'),
        backgroundColor: Colors.white,
      ),
      body: loading
          ? const Center(child: CircularProgressIndicator(color: green))
          : error != null
              ? Center(child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Text(error!, textAlign: TextAlign.center),
                ))
              : Column(children: [
                  Expanded(child: ListView(
                    padding: const EdgeInsets.all(20),
                    children: [
                      Text(widget.serviceTitle, style: const TextStyle(
                        fontSize: 19, fontWeight: FontWeight.w900, color: ink,
                      )),
                      const SizedBox(height: 6),
                      const Text(
                        'You can complete these details now or return to them before checkout.',
                        style: TextStyle(color: muted, fontSize: 13),
                      ),
                      const SizedBox(height: 22),
                      if (service?.categoryRootSlug.toLowerCase() == 'electrical') ...[
                      const Text('Issue photo (optional)', style: TextStyle(
                        fontSize: 14, fontWeight: FontWeight.w800, color: ink,
                      )),
                      const SizedBox(height: 8),
                      if (selectedPhoto != null)
                        ClipRRect(
                          borderRadius: BorderRadius.circular(12),
                          child: Image.file(selectedPhoto!, height: 170, fit: BoxFit.cover),
                        )
                      else if (widget.hasIssuePhoto && !removeExistingPhoto)
                        Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: const Color(0xFFF4F6F3),
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: const Row(children: [
                            Icon(Icons.check_circle, color: green),
                            SizedBox(width: 8),
                            Text('A photo is attached to this service'),
                          ]),
                        ),
                      Wrap(
                        spacing: 8,
                        children: [
                          OutlinedButton.icon(
                            onPressed: saving ? null : () => _pickIssuePhoto(ImageSource.camera),
                            icon: const Icon(Icons.camera_alt_outlined),
                            label: const Text('Camera'),
                          ),
                          OutlinedButton.icon(
                            onPressed: saving ? null : () => _pickIssuePhoto(ImageSource.gallery),
                            icon: const Icon(Icons.photo_library_outlined),
                            label: const Text('Gallery'),
                          ),
                          if ((widget.hasIssuePhoto && !removeExistingPhoto) || selectedPhoto != null)
                            TextButton.icon(
                              onPressed: saving ? null : () => setState(() {
                                selectedPhoto = null;
                                removeExistingPhoto = true;
                              }),
                              icon: const Icon(Icons.delete_outline),
                              label: const Text('Remove'),
                            ),
                        ],
                      ),
                      const SizedBox(height: 16),
                      const Text('Issue description (optional)', style: TextStyle(
                        fontSize: 14, fontWeight: FontWeight.w800, color: ink,
                      )),
                      const SizedBox(height: 8),
                      TextField(
                        controller: notesController,
                        minLines: 2,
                        maxLines: 4,
                        maxLength: 1000,
                        decoration: const InputDecoration(
                          hintText: 'Describe the problem or add instructions',
                          border: OutlineInputBorder(),
                        ),
                      ),
                      ],
                      const SizedBox(height: 22),
                      if (service?.supportsProfessionalPreference == true) ...[
                        const Text('Professional preference', style: TextStyle(
                          fontSize: 14, fontWeight: FontWeight.w800, color: ink,
                        )),
                        const SizedBox(height: 8),
                        if (service?.requiresFemaleWorker == true)
                          const Text('This service requires a female professional.',
                            style: TextStyle(color: muted, fontSize: 13))
                        else ...[
                          RadioListTile<String>(
                            contentPadding: EdgeInsets.zero,
                            title: const Text('No preference'),
                            value: 'any',
                            groupValue: categoryAnswers['professional_preference']?.toString() ?? 'any',
                            onChanged: (value) => setState(() => categoryAnswers['professional_preference'] = value),
                          ),
                          RadioListTile<String>(
                            contentPadding: EdgeInsets.zero,
                            title: const Text('Female professional'),
                            value: 'female',
                            groupValue: categoryAnswers['professional_preference']?.toString() ?? 'any',
                            onChanged: (value) => setState(() => categoryAnswers['professional_preference'] = value),
                          ),
                        ],
                        const SizedBox(height: 12),
                      ],
                      for (final field in visibleFields) ...[
                        _field(field),
                        const SizedBox(height: 14),
                      ],
                      if (visibleFields.isEmpty)
                        const Text('No additional preferences are required for this service.',
                          style: TextStyle(color: muted)),
                    ],
                  )),
                  SafeArea(top: false, child: Padding(
                    padding: const EdgeInsets.all(18),
                    child: SizedBox(
                      width: double.infinity,
                      child: FilledButton(
                        onPressed: saving ? null : _save,
                        style: FilledButton.styleFrom(backgroundColor: green, padding: const EdgeInsets.symmetric(vertical: 15)),
                        child: saving
                            ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                            : const Text('Save preferences'),
                      ),
                    ),
                  )),
                ]),
    );
  }

  Widget _field(CatalogFormField field) {
    final decoration = InputDecoration(
      labelText: field.isRequired ? '${field.label} *' : field.label,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(13), borderSide: const BorderSide(color: line)),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(13), borderSide: const BorderSide(color: line)),
    );
    if (field.fieldType == 'select' || field.fieldType == 'choice') {
      final options = field.options.map((raw) {
        if (raw is Map) {
          return MapEntry(
            raw['value']?.toString() ?? raw['label']?.toString() ?? '',
            raw['label']?.toString() ?? raw['value']?.toString() ?? '',
          );
        }
        return MapEntry(raw.toString(), raw.toString());
      }).where((entry) => entry.key.isNotEmpty).toList();
      return DropdownButtonFormField<String>(
        value: answers[field.key]?.toString(),
        decoration: decoration,
        items: options.map((option) => DropdownMenuItem(
          value: option.key, child: Text(option.value),
        )).toList(),
        onChanged: (value) => _setAnswer(field.key, value),
      );
    }
    if (field.fieldType == 'photo') {
      final selected = selectedFormPhotos[field.key];
      final attached = answers[field.key]?.toString() == 'uploaded' &&
          !removedFormPhotos.contains(field.key);
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(field.isRequired ? '${field.label} *' : field.label,
              style: const TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          if (selected != null)
            ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: Image.file(selected, height: 140, width: double.infinity, fit: BoxFit.cover),
            )
          else if (attached)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: const Color(0xFFF3F6F3),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Row(children: [
                Icon(Icons.check_circle_outline, color: green),
                SizedBox(width: 8),
                Expanded(child: Text('Photo attached securely')),
              ]),
            ),
          if (selected != null || attached)
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                onPressed: saving ? null : () {
                  setState(() {
                    selectedFormPhotos.remove(field.key);
                    removedFormPhotos.add(field.key);
                    answers.remove(field.key);
                  });
                },
                icon: const Icon(Icons.delete_outline),
                label: const Text('Remove photo'),
              ),
            )
          else
            Row(children: [
              Expanded(child: OutlinedButton.icon(
                onPressed: saving ? null : () => _pickFormPhoto(field.key, ImageSource.camera),
                icon: const Icon(Icons.camera_alt_outlined),
                label: const Text('Camera'),
              )),
              const SizedBox(width: 8),
              Expanded(child: OutlinedButton.icon(
                onPressed: saving ? null : () => _pickFormPhoto(field.key, ImageSource.gallery),
                icon: const Icon(Icons.photo_library_outlined),
                label: const Text('Gallery'),
              )),
            ]),
        ],
      );
    }
    if (field.fieldType == 'date') {
      final selected = DateTime.tryParse(answers[field.key]?.toString() ?? '');
      return InkWell(
        onTap: () async {
          final picked = await showDatePicker(
            context: context,
            initialDate: selected ?? DateTime.now(),
            firstDate: DateTime(1900),
            lastDate: DateTime(2100),
          );
          if (picked != null) {
            _setAnswer(field.key, '${picked.year.toString().padLeft(4, '0')}-${picked.month.toString().padLeft(2, '0')}-${picked.day.toString().padLeft(2, '0')}');
          }
        },
        child: InputDecorator(
          decoration: decoration,
          child: Text(selected == null ? 'Select date' : '${selected.day}/${selected.month}/${selected.year}'),
        ),
      );
    }
    final controller = controllers.putIfAbsent(
      field.key,
      () => TextEditingController(text: answers[field.key]?.toString() ?? ''),
    );
    return TextField(
      controller: controller,
      decoration: decoration,
      keyboardType: field.fieldType == 'number' ? TextInputType.number : TextInputType.text,
      maxLines: field.fieldType == 'textarea' ? 3 : 1,
      onChanged: (value) => _setAnswer(field.key, value),
    );
  }
}
