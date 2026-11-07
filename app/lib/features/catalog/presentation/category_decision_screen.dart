import 'package:flutter/material.dart';

/// Collects category-level choices before the customer browses individual services.
/// The fields are configured in Category.flow_steps by the AIRway admin.
class CategoryDecisionScreen extends StatefulWidget {
  final String categoryTitle;
  final List<Map<String, dynamic>> steps;

  const CategoryDecisionScreen({
    super.key,
    required this.categoryTitle,
    required this.steps,
  });

  @override
  State<CategoryDecisionScreen> createState() => _CategoryDecisionScreenState();
}

class _CategoryDecisionScreenState extends State<CategoryDecisionScreen> {
  static const green = Color(0xFF315C46);
  static const ink = Color(0xFF1E2923);
  static const muted = Color(0xFF748078);
  static const line = Color(0xFFEAE6DE);

  final _formKey = GlobalKey<FormState>();
  final Map<String, dynamic> _answers = {};

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFFFFFF),
      appBar: AppBar(
        title: Text(widget.categoryTitle),
        backgroundColor: Colors.white,
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
          children: [
            const Text(
              'Let’s personalise your service',
              style: TextStyle(fontSize: 23, fontWeight: FontWeight.w900, color: ink),
            ),
            const SizedBox(height: 6),
            const Text(
              'Choose a few details so we can show the right services and options.',
              style: TextStyle(color: muted, height: 1.45),
            ),
            const SizedBox(height: 22),
            for (final step in widget.steps) ...[
              _field(step),
              const SizedBox(height: 18),
            ],
            const SizedBox(height: 8),
            FilledButton(
              onPressed: _continue,
              style: FilledButton.styleFrom(
                backgroundColor: green,
                padding: const EdgeInsets.symmetric(vertical: 16),
              ),
              child: const Text('Continue to services'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _field(Map<String, dynamic> step) {
    final key = step['key']?.toString() ?? '';
    final title = step['title']?.toString() ?? key;
    final description = step['description']?.toString();
    final type = step['type']?.toString() ?? 'select';
    final isRequired = step['required'] != false;
    final options = (step['options'] as List? ?? [])
        .map((value) => value.toString())
        .toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title + (isRequired ? ' *' : ''),
          style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: ink),
        ),
        if (description != null && description.isNotEmpty) ...[
          const SizedBox(height: 4),
          Text(description, style: const TextStyle(fontSize: 12, color: muted)),
        ],
        const SizedBox(height: 9),
        if (type == 'select' && options.isNotEmpty)
          DropdownButtonFormField<String>(
            value: _answers[key]?.toString(),
            decoration: _decoration('Choose $title'),
            items: options.map((value) => DropdownMenuItem(value: value, child: Text(value))).toList(),
            onChanged: (value) => setState(() => _answers[key] = value),
            validator: isRequired ? (value) => value == null || value.isEmpty ? 'Please choose $title' : null : null,
          )
        else
          TextFormField(
            initialValue: _answers[key]?.toString() ?? '',
            keyboardType: type == 'number' ? TextInputType.number : TextInputType.text,
            maxLines: type == 'textarea' ? 3 : 1,
            decoration: _decoration('Enter $title'),
            onChanged: (value) => _answers[key] = value,
            validator: required ? (value) => value == null || value.trim().isEmpty ? 'Please enter $title' : null : null,
          ),
      ],
    );
  }

  InputDecoration _decoration(String hint) => InputDecoration(
    hintText: hint,
    filled: true,
    fillColor: const Color(0xFFF8FAF8),
    border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: line)),
    enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: line)),
    focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: green, width: 1.5)),
  );

  void _continue() {
    if (!_formKey.currentState!.validate()) return;
    Navigator.pop(context, Map<String, dynamic>.from(_answers));
  }
}
