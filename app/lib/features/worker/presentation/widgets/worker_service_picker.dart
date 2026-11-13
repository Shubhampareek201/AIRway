import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';

class WorkerServicePicker extends StatefulWidget {
  final List<Service> services;
  final Set<int> selectedIds;
  final Map<int, Set<String>> capabilities;
  final ValueChanged<int> onServiceAdded;
  final ValueChanged<int> onServiceRemoved;
  final void Function(int, String, bool) onCapabilityChanged;
  final String? errorText;
  const WorkerServicePicker({super.key, required this.services, required this.selectedIds, required this.capabilities, required this.onServiceAdded, required this.onServiceRemoved, required this.onCapabilityChanged, this.errorText});
  @override
  State<WorkerServicePicker> createState() => _WorkerServicePickerState();
}

class _WorkerServicePickerState extends State<WorkerServicePicker> {
  int _step = 0;
  String? _root;
  int? _skillServiceId;
  String _audience = 'all';
  String _query = '';
  String _rootName(Service s) => s.categoryRootName.trim().isEmpty ? s.categoryName : s.categoryRootName;
  List<String> get _roots => widget.services.map(_rootName).toSet().toList()..sort();
  List<Service> get _rootServices => widget.services.where((s) => _rootName(s) == _root).toList();
  bool get _isBeauty => _rootServices.any((s) => s.categoryRootSlug == 'beauty');
  List<Service> get _visibleServices {
    final q = _query.trim().toLowerCase();
    return _rootServices.where((s) {
      final audienceOk = !_isBeauty || _audience == 'all' || s.audience.toLowerCase() == _audience;
      return audienceOk && (q.isEmpty || s.title.toLowerCase().contains(q) || s.categoryName.toLowerCase().contains(q));
    }).toList();
  }
  List<String> _tasks(Service s) => <String>{...s.variants.expand((v) => v.includedTasks), ...s.addons.map((a) => a.title)}.map((v) => v.trim()).where((v) => v.isNotEmpty).toList()..sort();
  void _toggle(int id, bool value) {
    if (value) { widget.onServiceAdded(id); setState(() => _skillServiceId = id); }
    else { widget.onServiceRemoved(id); if (_skillServiceId == id) setState(() => _skillServiceId = null); }
  }

  @override
  Widget build(BuildContext context) {
    final selected = widget.services.where((s) => widget.selectedIds.contains(s.id)).toList();
    Service? current;
    for (final s in selected) { if (s.id == _skillServiceId) current = s; }
    current ??= selected.isEmpty ? null : selected.first;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [_dot(0, 'Category'), const Expanded(child: Divider()), _dot(1, 'Services'), const Expanded(child: Divider()), _dot(2, 'Skills')]),
      const SizedBox(height: 14),
      if (widget.errorText != null) Padding(padding: const EdgeInsets.only(bottom: 8), child: Text(widget.errorText!, style: const TextStyle(color: Colors.red, fontSize: 12))),
      if (_step == 0) ...[
        const Text('What type of work can you do?', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
        const SizedBox(height: 4),
        const Text('Choose a category to see its services.', style: TextStyle(color: AirwayColors.textSecondary)),
        const SizedBox(height: 12),
        ..._roots.map((root) {
          final rows = widget.services.where((s) => _rootName(s) == root);
          final count = rows.length;
          final chosen = rows.where((s) => widget.selectedIds.contains(s.id)).length;
          return Card(margin: const EdgeInsets.only(bottom: 8), child: ListTile(
            leading: CircleAvatar(backgroundColor: AirwayColors.primary.withAlpha(20), child: const Icon(Icons.category_outlined, color: AirwayColors.primary)),
            title: Text(root, style: const TextStyle(fontWeight: FontWeight.w700)),
            subtitle: Text(chosen.toString() + ' selected · ' + count.toString() + ' available'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => setState(() { _root = root; _step = 1; _query = ''; _audience = 'all'; }),
          ));
        }),
      ] else if (_step == 1) ...[
        Row(children: [IconButton(onPressed: () => setState(() => _step = 0), icon: const Icon(Icons.arrow_back)), Expanded(child: Text(_root ?? 'Services', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800))), Text(widget.selectedIds.length.toString() + ' selected', style: const TextStyle(color: AirwayColors.primary, fontWeight: FontWeight.w700))]),
        TextField(onChanged: (v) => setState(() => _query = v), decoration: const InputDecoration(prefixIcon: Icon(Icons.search), hintText: 'Find a service', border: OutlineInputBorder(), isDense: true)),
        if (_isBeauty) ...[
          const SizedBox(height: 10),
          SegmentedButton<String>(segments: const [ButtonSegment(value: 'all', label: Text('All')), ButtonSegment(value: 'women', label: Text('Women')), ButtonSegment(value: 'men', label: Text('Men')), ButtonSegment(value: 'unisex', label: Text('Unisex'))], selected: {_audience}, showSelectedIcon: false, onSelectionChanged: (v) => setState(() => _audience = v.first)),
        ],
        const SizedBox(height: 8),
        if (_visibleServices.isEmpty) const Padding(padding: EdgeInsets.all(20), child: Center(child: Text('No services found in this group.')))
        else ..._visibleServices.map((s) => Card(margin: const EdgeInsets.only(bottom: 6), child: CheckboxListTile(value: widget.selectedIds.contains(s.id), onChanged: (v) => _toggle(s.id, v == true), title: Text(s.title, style: const TextStyle(fontWeight: FontWeight.w600)), subtitle: Text(s.categoryName), controlAffinity: ListTileControlAffinity.leading))),
        const SizedBox(height: 8),
        SizedBox(width: double.infinity, child: FilledButton(onPressed: widget.selectedIds.isEmpty ? null : () => setState(() { _step = 2; _skillServiceId = selected.isEmpty ? null : selected.first.id; }), child: Text('Continue · ' + widget.selectedIds.length.toString() + ' selected'))),
      ] else ...[
        Row(children: [IconButton(onPressed: () => setState(() => _step = 1), icon: const Icon(Icons.arrow_back)), const Expanded(child: Text('Choose your skills', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800)))]),
        const Text('Select only the work you are trained to perform. Changed skills may need admin verification.', style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12)),
        const SizedBox(height: 10),
        if (selected.isEmpty) const Text('Go back and select at least one service.')
        else ...[
          DropdownButtonFormField<int>(value: current?.id, decoration: const InputDecoration(labelText: 'Service', border: OutlineInputBorder(), isDense: true), items: selected.map((s) => DropdownMenuItem(value: s.id, child: Text(s.title, overflow: TextOverflow.ellipsis))).toList(), onChanged: (id) => setState(() => _skillServiceId = id)),
          const SizedBox(height: 12),
          if (current != null) Builder(builder: (context) {
            final tasks = _tasks(current!);
            final chosen = widget.capabilities.putIfAbsent(current!.id, () => <String>{});
            if (tasks.isEmpty) return const Text('No task options are configured for this service. You can still provide the service; AIRway may verify skills separately.', style: TextStyle(color: AirwayColors.textSecondary));
            return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(chosen.length.toString() + ' of ' + tasks.length.toString() + ' work options selected', style: const TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 8),
              ...tasks.map((task) => CheckboxListTile(dense: true, contentPadding: EdgeInsets.zero, value: chosen.contains(task), title: Text(task), onChanged: (v) => widget.onCapabilityChanged(current!.id, task, v == true))),
            ]);
          }),
          OutlinedButton.icon(onPressed: () => setState(() => _step = 1), icon: const Icon(Icons.add), label: const Text('Add or change services')),
        ],
      ],
      if (_step != 1) ...[
        const SizedBox(height: 12),
        Container(width: double.infinity, padding: const EdgeInsets.all(12), decoration: BoxDecoration(color: AirwayColors.primary.withAlpha(12), borderRadius: BorderRadius.circular(12)), child: Text(widget.selectedIds.length.toString() + ' services selected', style: const TextStyle(fontWeight: FontWeight.w700, color: AirwayColors.primary))),
      ],
    ]);
  }

  Widget _dot(int index, String label) {
    final active = _step == index, done = _step > index;
    final color = active || done ? AirwayColors.primary : AirwayColors.textSecondary;
    return Padding(padding: const EdgeInsets.symmetric(horizontal: 4), child: Column(mainAxisSize: MainAxisSize.min, children: [
      CircleAvatar(radius: 13, backgroundColor: color.withAlpha(24), child: Icon(done ? Icons.check : Icons.circle, size: 12, color: color)),
      const SizedBox(height: 3),
      Text(label, style: TextStyle(fontSize: 10, color: color, fontWeight: active ? FontWeight.w800 : FontWeight.w500)),
    ]));
  }
}
