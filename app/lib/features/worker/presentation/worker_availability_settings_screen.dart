import 'package:flutter/material.dart';
import 'package:airway/core/localization/airway_text.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/worker/data/worker_api.dart';

class WorkerAvailabilitySettingsScreen extends StatefulWidget {
  const WorkerAvailabilitySettingsScreen({super.key});

  @override
  State<WorkerAvailabilitySettingsScreen> createState() =>
      _WorkerAvailabilitySettingsScreenState();
}

class _WorkerAvailabilitySettingsScreenState
    extends State<WorkerAvailabilitySettingsScreen> {
  static const _days = [
    'Monday', 'Tuesday', 'Wednesday', 'Thursday',
    'Friday', 'Saturday', 'Sunday',
  ];
  final Map<int, Map<String, String>> _hours = {};
  bool _loading = true;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final rows = await WorkerApi.getWorkerSchedules();
      if (!mounted) return;
      setState(() {
        _hours.clear();
        for (final row in rows) {
          if (row['is_active'] == false) continue;
          final day = int.tryParse(row['weekday']?.toString() ?? '');
          if (day == null || day < 0 || day > 6) continue;
          _hours[day] = {
            'start': (row['start_time']?.toString() ?? '09:00').substring(0, 5),
            'end': (row['end_time']?.toString() ?? '18:00').substring(0, 5),
          };
        }
        _loading = false;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e.toString().replaceFirst('Exception: ', '');
      });
    }
  }

  Future<void> _pickTime(int day, String key) async {
    final current = _hours[day]![key]!;
    final parts = current.split(':');
    final picked = await showTimePicker(
      context: context,
      initialTime: TimeOfDay(hour: int.parse(parts[0]), minute: int.parse(parts[1])),
    );
    if (picked == null || !mounted) return;
    setState(() {
      _hours[day]![key] =
          '${picked.hour.toString().padLeft(2, '0')}:${picked.minute.toString().padLeft(2, '0')}';
    });
  }

  String _displayTime(String value) {
    final parts = value.split(':');
    return TimeOfDay(hour: int.parse(parts[0]), minute: int.parse(parts[1]))
        .format(context);
  }

  Future<void> _save() async {
    if (_hours.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Select at least one working day.')),
      );
      return;
    }
    for (final entry in _hours.entries) {
      if (entry.value['start']!.compareTo(entry.value['end']!) >= 0) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('${_days[entry.key]}: end time must be after start time.')),
        );
        return;
      }
    }
    setState(() => _saving = true);
    try {
      final rows = _hours.entries.map((entry) => {
        'weekday': entry.key,
        'start_time': entry.value['start'],
        'end_time': entry.value['end'],
        'is_active': true,
      }).toList()..sort((a, b) => (a['weekday'] as int).compareTo(b['weekday'] as int));
      final saved = await WorkerApi.updateWorkerSchedules(rows);
      if (!mounted) return;
      setState(() {
        _hours.clear();
        for (final row in saved) {
          final day = int.tryParse(row['weekday']?.toString() ?? '');
          if (day == null || day < 0 || day > 6 || row['is_active'] == false) continue;
          _hours[day] = {
            'start': row['start_time'].toString().substring(0, 5),
            'end': row['end_time'].toString().substring(0, 5),
          };
        }
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Working hours updated.')),
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(
            AirwayText.tr('Could not update working hours: $e', 'कार्य समय अपडेट नहीं हो सका: $e'),
          )),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(AirwayText.tr('Availability settings', 'उपलब्धता सेटिंग्स'))),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(mainAxisSize: MainAxisSize.min, children: [
                    Text(_error!, textAlign: TextAlign.center),
                    const SizedBox(height: 12),
                    OutlinedButton.icon(onPressed: () {
                      setState(() { _loading = true; _error = null; });
                      _load();
                    }, icon: const Icon(Icons.refresh), label: const Text('Try again')),
                  ]),
                ))
              : ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    Card(child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        const Text('Set your weekly working hours',
                            style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
                        const SizedBox(height: 6),
                        Text(
                          'You can receive new offers only when you are online and within these approved working hours. Going offline does not cancel jobs you have already accepted.',
                          style: TextStyle(color: AirwayColors.textSecondary, height: 1.4),
                        ),
                      ]),
                    )),
                    const SizedBox(height: 8),
                    ...List.generate(7, (day) {
                      final selected = _hours.containsKey(day);
                      return Card(
                        child: Column(children: [
                          CheckboxListTile(
                            value: selected,
                            title: Text(_days[day], style: const TextStyle(fontWeight: FontWeight.w700)),
                            onChanged: _saving ? null : (value) => setState(() {
                              if (value == true) {
                                _hours[day] = {'start': '09:00', 'end': '18:00'};
                              } else {
                                _hours.remove(day);
                              }
                            }),
                          ),
                          if (selected)
                            Padding(
                              padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
                              child: Row(children: [
                                Expanded(child: OutlinedButton(
                                  onPressed: _saving ? null : () => _pickTime(day, 'start'),
                                  child: Text('From ${_displayTime(_hours[day]!['start']!)}'),
                                )),
                                const SizedBox(width: 8),
                                Expanded(child: OutlinedButton(
                                  onPressed: _saving ? null : () => _pickTime(day, 'end'),
                                  child: Text('To ${_displayTime(_hours[day]!['end']!)}'),
                                )),
                              ]),
                            ),
                        ]),
                      );
                    }),
                    const SizedBox(height: 12),
                    FilledButton(
                      onPressed: _saving ? null : _save,
                      child: _saving
                          ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                          : const Text('Save working hours'),
                    ),
                  ],
                ),
    );
  }
}
