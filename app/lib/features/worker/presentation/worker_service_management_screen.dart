import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';
import 'package:airway/features/worker/data/worker_api.dart';
import 'package:airway/features/worker/data/worker_app_api.dart';
import 'package:airway/features/worker/data/worker_models.dart';
import 'package:airway/features/worker/presentation/widgets/worker_service_picker.dart';

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
    final inactiveRows = widget.profile.serviceItems.where((row) {
      final id = int.tryParse(row['service']?.toString() ?? '');
      return id != null && !_catalogue.any((service) => service.id == id);
    }).toList();
    return Scaffold(
      appBar: AppBar(title: const Text('My services')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(mainAxisSize: MainAxisSize.min, children: [
                    Text(_error!, textAlign: TextAlign.center),
                    const SizedBox(height: 12),
                    FilledButton(onPressed: _load, child: const Text('Try again')),
                  ]),
                ))
              : Column(children: [
                  Expanded(child: ListView(
                    padding: const EdgeInsets.fromLTRB(16, 16, 16, 20),
                    children: [
                      const Text('Manage the services you can provide', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
                      const SizedBox(height: 4),
                      const Text('Choose a category, select services, then review the skills you can perform.', style: TextStyle(color: AirwayColors.textSecondary)),
                      const SizedBox(height: 16),
                      WorkerServicePicker(
                        services: _catalogue,
                        selectedIds: _selected,
                        capabilities: _capabilities,
                        onServiceAdded: (id) => setState(() {
                          _selected.add(id);
                          _capabilities.putIfAbsent(id, () => <String>{});
                        }),
                        onServiceRemoved: (id) => setState(() {
                          _selected.remove(id);
                          _capabilities.remove(id);
                        }),
                        onCapabilityChanged: (id, task, selected) => setState(() {
                          final values = _capabilities.putIfAbsent(id, () => <String>{});
                          if (selected) { values.add(task); } else { values.remove(task); }
                        }),
                      ),
                      if (inactiveRows.isNotEmpty) ...[
                        const SizedBox(height: 20),
                        const Text('Unavailable services', style: TextStyle(fontWeight: FontWeight.w800)),
                        const SizedBox(height: 6),
                        ...inactiveRows.map((row) {
                          final id = int.tryParse(row['service']?.toString() ?? '');
                          return Card(child: ListTile(
                            leading: const Icon(Icons.info_outline, color: Colors.orange),
                            title: Text(row['service_title']?.toString() ?? 'Inactive service'),
                            subtitle: const Text('This service is no longer active. Remove it from your profile if you no longer provide it.'),
                            trailing: IconButton(
                              tooltip: 'Remove service',
                              onPressed: _saving || id == null ? null : () => setState(() { _selected.remove(id); }),
                              icon: const Icon(Icons.remove_circle_outline),
                            ),
                          ));
                        }),
                      ],
                    ],
                  )),
                  SafeArea(top: false, child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: SizedBox(width: double.infinity, child: FilledButton(
                      onPressed: _saving ? null : _save,
                      child: _saving ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)) : const Text('Save service changes'),
                    )),
                  )),
                ]),
    );
  }
}
