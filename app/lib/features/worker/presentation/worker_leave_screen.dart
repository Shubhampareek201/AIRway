import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/worker/data/worker_api.dart';

class WorkerLeaveScreen extends StatefulWidget {
  const WorkerLeaveScreen({super.key});

  @override
  State<WorkerLeaveScreen> createState() => _WorkerLeaveScreenState();
}

class _WorkerLeaveScreenState extends State<WorkerLeaveScreen> {
  final _reasonController = TextEditingController();
  List<Map<String, dynamic>> _leaves = [];
  DateTime? _startAt;
  DateTime? _endAt;
  bool _loading = true;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _reasonController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final rows = await WorkerApi.getLeaves();
      if (!mounted) return;
      setState(() {
        _leaves = rows;
        _loading = false;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e.toString();
      });
    }
  }

  Future<DateTime?> _chooseDate(DateTime? current, {required bool start}) async {
    final now = DateTime.now();
    final initial = current ?? now.add(const Duration(days: 1));
    final date = await showDatePicker(
      context: context,
      initialDate: initial.isBefore(now) ? now : initial,
      firstDate: DateTime(now.year, now.month, now.day),
      lastDate: start
          ? DateTime(now.year + 2)
          : (_startAt ?? now).add(const Duration(days: 90)),
    );
    if (date == null || !mounted) return null;
    final oldTime = current ?? DateTime(date.year, date.month, date.day, start ? 9 : 18);
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(oldTime),
    );
    if (time == null) return null;
    return DateTime(date.year, date.month, date.day, time.hour, time.minute);
  }

  Future<void> _submit() async {
    final start = _startAt;
    final end = _endAt;
    if (start == null || end == null || !end.isAfter(start)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Choose a valid leave start and end time.')),
      );
      return;
    }
    if (end.difference(start) > const Duration(days: 90)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('A leave request cannot exceed 90 days.')),
      );
      return;
    }
    setState(() => _saving = true);
    try {
      await WorkerApi.requestLeave(
        startAt: start,
        endAt: end,
        reason: _reasonController.text.trim(),
      );
      _reasonController.clear();
      setState(() {
        _startAt = null;
        _endAt = null;
      });
      await _load();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Leave request sent for Admin review.')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not submit leave request: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _cancel(Map<String, dynamic> leave) async {
    final id = int.tryParse(leave['id'].toString());
    if (id == null) return;
    try {
      await WorkerApi.cancelLeave(id);
      await _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not cancel leave: $e')),
        );
      }
    }
  }

  String _date(DateTime? value) =>
      value == null ? 'Select date and time' : DateFormat('dd MMM yyyy, hh:mm a').format(value);

  Color _statusColor(String status) => switch (status) {
    'approved' => Colors.green,
    'rejected' => AirwayColors.error,
    'cancelled' || 'expired' => Colors.grey,
    _ => Colors.orange,
  };

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Leave management')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text('Request time off', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                          const SizedBox(height: 6),
                          const Text('Requests are reviewed by AIRway Admin. Approved leave prevents new job assignments. Existing assigned jobs must be resolved before approval.'),
                          const SizedBox(height: 14),
                          OutlinedButton.icon(
                            onPressed: _saving ? null : () async {
                              final value = await _chooseDate(_startAt, start: true);
                              if (value != null && mounted) setState(() => _startAt = value);
                            },
                            icon: const Icon(Icons.event_available_outlined),
                            label: Text('Starts: ${_date(_startAt)}'),
                          ),
                          OutlinedButton.icon(
                            onPressed: _saving ? null : () async {
                              final value = await _chooseDate(_endAt, start: false);
                              if (value != null && mounted) setState(() => _endAt = value);
                            },
                            icon: const Icon(Icons.event_busy_outlined),
                            label: Text('Ends: ${_date(_endAt)}'),
                          ),
                          TextField(
                            controller: _reasonController,
                            maxLines: 2,
                            maxLength: 500,
                            decoration: const InputDecoration(
                              labelText: 'Reason (optional)',
                              border: OutlineInputBorder(),
                            ),
                          ),
                          const SizedBox(height: 8),
                          SizedBox(
                            width: double.infinity,
                            child: FilledButton(
                              onPressed: _saving ? null : _submit,
                              child: _saving
                                  ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                                  : const Text('Submit leave request'),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 18),
                  const Text('Your requests', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                  if (_error != null) Padding(
                    padding: const EdgeInsets.all(12),
                    child: Text(_error!, style: const TextStyle(color: AirwayColors.error)),
                  ),
                  if (_leaves.isEmpty)
                    const Padding(
                      padding: EdgeInsets.all(20),
                      child: Text('No leave requests yet.'),
                    ),
                  ..._leaves.map((leave) {
                    final status = leave['status']?.toString() ?? 'pending';
                    final start = DateTime.tryParse(leave['start_at']?.toString() ?? '')?.toLocal();
                    final end = DateTime.tryParse(leave['end_at']?.toString() ?? '')?.toLocal();
                    final canCancel = status == 'pending' ||
                        (status == 'approved' && start != null && start.isAfter(DateTime.now()));
                    final history = (leave['history'] as List?)?.whereType<Map>().toList() ?? [];
                    return Card(
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(children: [
                              Expanded(child: Text('${_date(start)} – ${_date(end)}', style: const TextStyle(fontWeight: FontWeight.w700))),
                              Chip(
                                label: Text(status.toUpperCase()),
                                labelStyle: TextStyle(color: _statusColor(status), fontSize: 11, fontWeight: FontWeight.w700),
                                backgroundColor: _statusColor(status).withValues(alpha: 0.10),
                                side: BorderSide.none,
                              ),
                            ]),
                            if ((leave['reason'] ?? '').toString().isNotEmpty) Text('Reason: ${leave['reason']}'),
                            if ((leave['admin_note'] ?? '').toString().isNotEmpty) Text('Admin note: ${leave['admin_note']}'),
                            for (final item in history)
                              Padding(
                                padding: const EdgeInsets.only(top: 4),
                                child: Text(
                                  '${item['to_status']}: ${item['note'] ?? ''}',
                                  style: Theme.of(context).textTheme.bodySmall,
                                ),
                              ),
                            if (canCancel) Align(
                              alignment: Alignment.centerRight,
                              child: TextButton.icon(
                                onPressed: () => _cancel(leave),
                                icon: const Icon(Icons.cancel_outlined),
                                label: const Text('Cancel request'),
                              ),
                            ),
                          ],
                        ),
                      ),
                    );
                  }),
                ],
              ),
            ),
    );
  }
}
