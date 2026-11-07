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
    final options = (step['options'] as List? ?? []).map((item) {
      if (item is Map) {
        final option = Map<String, dynamic>.from(item);
        final value = option['value']?.toString() ?? option['label']?.toString() ?? '';
        return {
          'value': value,
          'label': option['label']?.toString() ?? value,
          'image': option['image']?.toString(),
        };
      }
      final value = item.toString();
      return {'value': value, 'label': value, 'image': null};
    }).where((item) => (item['value'] as String).isNotEmpty).toList();

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
        const SizedBox(height: 10),
        if ((type == 'select' || type == 'choice') && options.isNotEmpty)
          LayoutBuilder(
            builder: (context, constraints) {
              final cardWidth = (constraints.maxWidth - 10) / 2;
              return Wrap(
                spacing: 10,
                runSpacing: 10,
                children: options.map((option) {
                  final value = option['value'] as String;
                  final image = option['image'] as String?;
                  final selected = _answers[key]?.toString() == value;
                  return InkWell(
                    onTap: () => setState(() => _answers[key] = value),
                    borderRadius: BorderRadius.circular(14),
                    child: Container(
                      width: cardWidth,
                      decoration: BoxDecoration(
                        color: selected ? const Color(0xFFEAF1EA) : Colors.white,
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(color: selected ? green : line, width: selected ? 2 : 1),
                      ),
                      clipBehavior: Clip.antiAlias,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          if (image != null && image.isNotEmpty)
                            Image.network(
                              image,
                              height: 92,
                              fit: BoxFit.cover,
                              errorBuilder: (_, __, ___) => _optionPlaceholder(),
                            )
                          else
                            _optionPlaceholder(),
                          Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 11),
                            child: Row(
                              children: [
                                Expanded(
                                  child: Text(
                                    option['label'] as String,
                                    style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: ink),
                                  ),
                                ),
                                if (selected) const Icon(Icons.check_circle, color: green, size: 18),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                }).toList(),
              );
            },
          )
        else
          TextFormField(
            initialValue: _answers[key]?.toString() ?? '',
            keyboardType: type == 'number' ? TextInputType.number : TextInputType.text,
            maxLines: type == 'textarea' ? 3 : 1,
            decoration: _decoration('Enter $title'),
            onChanged: (value) => _answers[key] = value,
          ),
      ],
    );
  }

  Widget _optionPlaceholder() => Container(
    height: 92,
    color: const Color(0xFFF1F5F1),
    alignment: Alignment.center,
    child: const Icon(Icons.photo_outlined, color: muted, size: 30),
  );

  InputDecoration _decoration(String hint) => InputDecoration(
    hintText: hint,
    filled: true,
    fillColor: const Color(0xFFF8FAF8),
    border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: line)),
    enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: line)),
    focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: green, width: 1.5)),
  );

  void _continue() {
    final missing = widget.steps.where((step) {
      if (step['required'] == false) return false;
      final key = step['key']?.toString() ?? '';
      return (_answers[key]?.toString().trim().isEmpty ?? true);
    }).toList();
    if (missing.isNotEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Please choose or enter: ${missing.first['title'] ?? missing.first['key']}')),
      );
      return;
    }
    Navigator.pop(context, Map<String, dynamic>.from(_answers));
  }
}
