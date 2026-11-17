import 'package:flutter/material.dart';
import 'package:airway/core/localization/airway_text.dart';
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
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(AirwayText.tr('Your service list has been updated.', 'आपकी सेवा सूची अपडेट हो गई है।'))));
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(AirwayText.tr('Some service changes could not be saved: $e', 'कुछ सेवा बदलाव सेव नहीं हो सके: $e'))));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final inactiveRows = widget.profile.serviceItems.where((row) {
      final id = int.tryParse(row['service']?.toString() ?? '');
      return id != null && !_catalogue.any((service) => service.id == id);
    }).toList();
    return Scaffold(
      appBar: AppBar(title: Text(AirwayText.tr('My services', 'मेरी सेवाएँ'))),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(mainAxisSize: MainAxisSize.min, children: [
                    Text(_error!, textAlign: TextAlign.center),
                    const SizedBox(height: 12),
                    FilledButton(onPressed: _load, child: Text(AirwayText.tr('Try again', 'फिर कोशिश करें'))),
                  ]),
                ))
              : Column(children: [
                  Expanded(child: ListView(
                    padding: const EdgeInsets.fromLTRB(16, 16, 16, 20),
                    children: [
                      Text(AirwayText.tr('Manage the services you can provide', 'वे सेवाएँ प्रबंधित करें जो आप दे सकते हैं'), style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
                      const SizedBox(height: 4),
                      Text(AirwayText.tr('Choose a category, select services, then review the skills you can perform.', 'श्रेणी चुनें, सेवाएँ चुनें और फिर अपने कौशल की समीक्षा करें।'), style: TextStyle(color: AirwayColors.textSecondary)),
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
                        Text(AirwayText.tr('Unavailable services', 'अनुपलब्ध सेवाएँ'), style: TextStyle(fontWeight: FontWeight.w800)),
                        const SizedBox(height: 6),
                        ...inactiveRows.map((row) {
                          final id = int.tryParse(row['service']?.toString() ?? '');
                          return Card(child: ListTile(
                            leading: const Icon(Icons.info_outline, color: Colors.orange),
                            title: Text(row['service_title']?.toString() ?? 'Inactive service'),
                            subtitle: Text(AirwayText.tr('This service is no longer active. Remove it from your profile if you no longer provide it.', 'यह सेवा अब सक्रिय नहीं है। यदि आप इसे नहीं देते, तो अपनी प्रोफ़ाइल से हटाएँ।')),
                            trailing: IconButton(
                              tooltip: AirwayText.tr('Remove service', 'सेवा हटाएँ'),
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
                      child: _saving ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)) : Text(AirwayText.tr('Save service changes', 'सेवा बदलाव सेव करें')),
                    )),
                  )),
                ]),
    );
  }
}
