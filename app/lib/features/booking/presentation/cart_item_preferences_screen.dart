import 'package:flutter/material.dart';
import 'package:airway/features/catalog/data/catalog_api.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';
import 'package:airway/features/booking/data/booking_api.dart';

class CartItemPreferencesScreen extends StatefulWidget {
  final int cartItemId;
  final int serviceId;
  final String serviceTitle;
  final Map<String, dynamic> categoryAnswers;
  final Map<String, dynamic> initialAnswers;

  const CartItemPreferencesScreen({
    super.key,
    required this.cartItemId,
    required this.serviceId,
    required this.serviceTitle,
    required this.categoryAnswers,
    required this.initialAnswers,
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
  final Map<String, TextEditingController> controllers = {};

  @override
  void initState() {
    super.initState();
    answers.addAll(widget.initialAnswers);
    _load();
  }

  @override
  void dispose() {
    for (final controller in controllers.values) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final value = await CatalogApi.getService(
        widget.serviceId,
        categoryAnswers: widget.categoryAnswers,
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
    final combined = <String, dynamic>{...widget.categoryAnswers, ...answers};
    return (service?.formFields ?? const <CatalogFormField>[])
        .where((field) => !widget.categoryAnswers.containsKey(field.key))
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
            controllers.remove(key)?.dispose();
          }
          changed = true;
        }
      }
    });
  }

  Future<void> _save() async {
    for (final field in visibleFields) {
      final value = answers[field.key];
      if (field.isRequired && (value == null || value.toString().trim().isEmpty)) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Please complete: ${field.label}')),
        );
        return;
      }
    }
    setState(() => saving = true);
    try {
      await BookingApi.updateCartItem(
        itemId: widget.cartItemId,
        data: {'form_answers': answers, 'category_answers': widget.categoryAnswers},
      );
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
