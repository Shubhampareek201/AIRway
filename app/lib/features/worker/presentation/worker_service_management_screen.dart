import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';
import 'package:airway/features/worker/data/worker_api.dart';
import 'package:airway/features/worker/data/worker_app_api.dart';
import 'package:airway/features/worker/data/worker_models.dart';

class WorkerServiceManagementScreen extends StatefulWidget {
  final WorkerProfile profile;
  const WorkerServiceManagementScreen({super.key, required this.profile});

  @override
  State<WorkerServiceManagementScreen> createState() => _WorkerServiceManagementScreenState();
}

class _WorkerServiceManagementScreenState extends State<WorkerServiceManagementScreen> {
  List<Service> _catalogue = [];
  late final Set<int> _selected = widget.profile.serviceItems
      .map((row) => int.tryParse(row['service']?.toString() ?? ''))
      .whereType<int>()
      .toSet();
  final Map<int, Set<String>> _capabilities = {};
  final _search = TextEditingController();
  bool _loading = true;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    for (final row in widget.profile.serviceItems) {
      final id = int.tryParse(row['service']?.toString() ?? '');
      if (id == null) continue;
      final tasks = row['capabilities'] as List? ?? const [];
      _capabilities[id] = tasks.map((value) => value.toString()).toSet();
    }
    _load();
  }

  @override
  void dispose() { _search.dispose(); super.dispose(); }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final services = await WorkerAppApi.fetchServicesForWorkerApplication();
      if (!mounted) return;
      setState(() { _catalogue = services; _loading = false; });
    } catch (e) {
      if (mounted) setState(() { _loading = false; _error = e.toString(); });
    }
  }

  List<Service> get _visible {
    final q = _search.text.trim().toLowerCase();
    if (q.isEmpty) return _catalogue;
    return _catalogue.where((s) =>
      s.title.toLowerCase().contains(q) ||
      s.categoryName.toLowerCase().contains(q) ||
      s.categoryRootName.toLowerCase().contains(q)
    ).toList();
  }

  Future<void> _save() async {
    if (_saving) return;
    setState(() => _saving = true);
    try {
      final current = widget.profile.serviceItems
          .map((row) => int.tryParse(row['service']?.toString() ?? ''))
          .whereType<int>().toSet();
      final add = _selected.difference(current);
      final remove = current.difference(_selected);
      // Add/update first so a failed selection never removes existing work.
      final existingRows = {
        for (final row in widget.profile.serviceItems)
          int.tryParse(row['service']?.toString() ?? ''): row,
      };
      for (final serviceId in _selected) {
        final matches = _catalogue.where((item) => item.id == serviceId).toList();
        final service = matches.isEmpty ? null : matches.first;
        if (service == null) continue;
        final tasks = (_capabilities[serviceId] ?? <String>{}).toList()..sort();
        final previous = existingRows[serviceId];
        final previousTasks = (previous?['capabilities'] as List? ?? const [])
            .map((value) => value.toString()).toList()..sort();
        if (add.contains(serviceId) || previousTasks.join('|') != tasks.join('|')) {
          await WorkerApi.addService(serviceId: serviceId, capabilities: tasks);
        }
      }
      for (final serviceId in remove) { await WorkerApi.removeService(serviceId); }
      if (!mounted) return;
      Navigator.pop(context, true);
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Your service list has been updated.')));
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Some service changes could not be saved: $e')));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Widget _serviceChip(Service service) {
    final selected = _selected.contains(service.id);
    return FilterChip(
      selected: selected,
      showCheckmark: true,
      selectedColor: AirwayColors.primary.withAlpha(28),
      label: Text(service.title),
      onSelected: _saving ? null : (value) => setState(() {
        if (value) {
          _selected.add(service.id);
          _capabilities.putIfAbsent(service.id, () => <String>{});
        } else {
          _selected.remove(service.id);
          _capabilities.remove(service.id);
        }
      }),
    );
  }

  @override
  Widget build(BuildContext context) {
    final grouped = <String, Map<String, List<Service>>>{};
    for (final service in _visible) {
      final root = service.categoryRootName.trim().isEmpty ? service.categoryName : service.categoryRootName;
      grouped.putIfAbsent(root, () => {});
      grouped[root]!.putIfAbsent(service.categoryName, () => []).add(service);
    }
    return Scaffold(
      appBar: AppBar(title: const Text('My services')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Padding(padding: const EdgeInsets.all(24), child: Column(mainAxisSize: MainAxisSize.min, children: [
                  Text(_error!, textAlign: TextAlign.center),
                  const SizedBox(height: 12),
                  FilledButton(onPressed: _load, child: const Text('Try again')),
                ])))
              : Column(children: [
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 14, 16, 8),
                    child: TextField(
                      controller: _search,
                      onChanged: (_) => setState(() {}),
                      decoration: const InputDecoration(prefixIcon: Icon(Icons.search), hintText: 'Search services or categories', border: OutlineInputBorder()),
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    child: Row(children: [
                      Expanded(child: Text('${_selected.length} services selected', style: const TextStyle(fontWeight: FontWeight.w800))),
                      TextButton(onPressed: _saving ? null : () => setState(() {
                        final visibleIds = _visible.map((s) => s.id);
                        if (visibleIds.every(_selected.contains)) { _selected.removeAll(visibleIds); } else { _selected.addAll(visibleIds); }
                      }), child: const Text('Select all shown')),
                    ]),
                  ),
                  Expanded(child: ListView(
                    padding: const EdgeInsets.fromLTRB(12, 0, 12, 16),
                    children: [
                      ...widget.profile.serviceItems.where((row) {
                        final id = int.tryParse(row['service']?.toString() ?? '');
                        return id != null && !_catalogue.any((service) => service.id == id);
                      }).map((row) {
                        final id = int.tryParse(row['service']?.toString() ?? '');
                        return Card(
                          child: ListTile(
                            leading: const Icon(Icons.info_outline, color: Colors.orange),
                            title: Text(row['service_title']?.toString() ?? 'Inactive service'),
                            subtitle: const Text('No longer available in the active catalogue. Remove it from your profile if you no longer provide it.'),
                            trailing: IconButton(
                              tooltip: 'Remove service',
                              onPressed: _saving || id == null ? null : () => setState(() => _selected.remove(id)),
                              icon: const Icon(Icons.remove_circle_outline),
                            ),
                          ),
                        );
                      }),
                      ...grouped.entries.map((root) {
                      final rootServices = root.value.values.expand((items) => items).toList();
                      final count = rootServices.where((s) => _selected.contains(s.id)).length;
                      return Card(
                        margin: const EdgeInsets.only(bottom: 10),
                        child: ExpansionTile(
                          title: Text(root.key, style: const TextStyle(fontWeight: FontWeight.w800)),
                          subtitle: Text('$count of ${rootServices.length} selected'),
                          children: root.value.entries.map((category) {
                            final ids = category.value.map((s) => s.id);
                            return Padding(
                              padding: const EdgeInsets.fromLTRB(14, 2, 14, 12),
                              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                                Row(children: [
                                  Expanded(child: Text(category.key, style: TextStyle(fontWeight: FontWeight.w700, color: AirwayColors.primary))),
                                  TextButton(onPressed: _saving ? null : () => setState(() {
                                    if (ids.every(_selected.contains)) { _selected.removeAll(ids); } else { _selected.addAll(ids); }
                                  }), child: const Text('Select all')),
                                ]),
                                Wrap(spacing: 7, runSpacing: 4, children: category.value.map(_serviceChip).toList()),
                              ]),
                            );
                          }).toList(),
                        ),
                      );
                    }).toList(),
                      ..._selected.where((id) => _catalogue.any((service) => service.id == id)).map((id) {
                        final service = _catalogue.firstWhere((item) => item.id == id);
                        final tasks = <String>{
                          ...service.variants.expand((variant) => variant.includedTasks),
                          ...service.addons.map((addon) => addon.title),
                        }.map((value) => value.trim()).where((value) => value.isNotEmpty).toList()..sort();
                        final selectedTasks = _capabilities.putIfAbsent(id, () => <String>{});
                        return Card(
                          margin: const EdgeInsets.only(bottom: 8),
                          child: ExpansionTile(
                            title: Text(service.title, style: const TextStyle(fontWeight: FontWeight.w700)),
                            subtitle: Text(tasks.isEmpty ? 'No task details configured' : '${selectedTasks.length} of ${tasks.length} work options selected'),
                            children: [
                              if (tasks.isEmpty)
                                const Padding(
                                  padding: EdgeInsets.all(14),
                                  child: Text('No task options have been configured for this service yet.'),
                                )
                              else
                                Padding(
                                  padding: const EdgeInsets.fromLTRB(14, 4, 14, 14),
                                  child: Wrap(
                                    spacing: 7,
                                    runSpacing: 4,
                                    children: tasks.map((task) => FilterChip(
                                      label: Text(task),
                                      selected: selectedTasks.contains(task),
                                      onSelected: _saving ? null : (value) => setState(() {
                                        if (value) { selectedTasks.add(task); } else { selectedTasks.remove(task); }
                                      }),
                                    )).toList(),
                                  ),
                                ),
                            ],
                          ),
                        );
                      }),
                    ],
                  )),
                  SafeArea(top: false, child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: SizedBox(width: double.infinity, child: FilledButton(
                      onPressed: _saving ? null : _save,
                      child: _saving ? const CircularProgressIndicator() : const Text('Save service changes'),
                    )),
                  )),
                ]),
    );
  }
}
