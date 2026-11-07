import 'dart:async';
import 'package:flutter/material.dart';
import 'package:airway/features/booking/data/booking_api.dart';

class BookingTrackingScreen extends StatefulWidget {
  final int bookingId;
  final String serviceTitle;
  final String initialStatus;

  const BookingTrackingScreen({
    super.key,
    required this.bookingId,
    required this.serviceTitle,
    this.initialStatus = 'pending',
  });

  @override
  State<BookingTrackingScreen> createState() => _BookingTrackingScreenState();
}

class _BookingTrackingScreenState extends State<BookingTrackingScreen> {
  static const _green = Color(0xFF075B43);
  static const _ink = Color(0xFF1E2923);
  static const _muted = Color(0xFF748078);
  static const _line = Color(0xFFEAE6DE);

  Timer? _poller;
  Map<String, dynamic> _tracking = {};
  String _status = 'pending';
  bool _loading = true;
  bool _refreshing = false;
  String? _error;

  bool get _terminal => _status == 'completed' ||
      _status == 'cancelled' || _status == 'disputed';

  @override
  void initState() {
    super.initState();
    _status = widget.initialStatus;
    _refresh();
    _poller = Timer.periodic(const Duration(seconds: 20), (_) {
      if (mounted && !_terminal) _refresh(silent: true);
    });
  }

  @override
  void dispose() {
    _poller?.cancel();
    super.dispose();
  }

  Future<void> _refresh({bool silent = false}) async {
    if (_refreshing) return;
    _refreshing = true;
    if (!silent && mounted) setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final result = await BookingApi.trackBooking(widget.bookingId);
      if (!mounted) return;
      setState(() {
        _tracking = result;
        _status = result['status']?.toString() ?? _status;
        _loading = false;
        _error = null;
      });
      if (_terminal) _poller?.cancel();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e.toString();
      });
    } finally {
      _refreshing = false;
    }
  }

  String get _statusText {
    switch (_status) {
      case 'pending': return 'Finding a professional';
      case 'confirmed': return 'Booking confirmed';
      case 'assigned': return 'Professional assigned';
      case 'in_progress': return 'Service in progress';
      case 'completed': return 'Service completed';
      case 'cancelled': return 'Booking cancelled';
      case 'disputed': return 'Booking under review';
      default: return _status.replaceAll('_', ' ');
    }
  }

  @override
  Widget build(BuildContext context) {
    final assigned = _tracking['is_assigned'] == true;
    final started = _status == 'in_progress' || _status == 'completed';
    final completed = _status == 'completed';
    final cancelled = _status == 'cancelled';
    return Scaffold(
      backgroundColor: const Color(0xFFF8FAF8),
      appBar: AppBar(
        backgroundColor: Colors.white,
        title: const Text('Track Service'),
        actions: [
          IconButton(
            onPressed: _loading ? null : () => _refresh(),
            icon: const Icon(Icons.refresh_rounded),
            tooltip: 'Refresh status',
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: _green))
          : RefreshIndicator(
              onRefresh: _refresh,
              child: ListView(
                padding: const EdgeInsets.all(20),
                children: [
                  Container(
                    padding: const EdgeInsets.all(18),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(18),
                      border: Border.all(color: _line),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(widget.serviceTitle,
                            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900, color: _ink)),
                        const SizedBox(height: 5),
                        Text('Booking #${widget.bookingId}',
                            style: const TextStyle(color: _muted, fontSize: 12)),
                        const SizedBox(height: 14),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                          decoration: BoxDecoration(
                            color: cancelled ? const Color(0xFFFFEEEE) : const Color(0xFFEAF1EA),
                            borderRadius: BorderRadius.circular(30),
                          ),
                          child: Text(_statusText,
                              style: TextStyle(fontWeight: FontWeight.w800,
                                  color: cancelled ? Colors.redAccent : _green)),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  if (_error != null)
                    Container(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(color: const Color(0xFFFFF5E9), borderRadius: BorderRadius.circular(14)),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        const Text('Could not refresh tracking', style: TextStyle(fontWeight: FontWeight.w800, color: _ink)),
                        const SizedBox(height: 5),
                        Text(_error!, style: const TextStyle(color: _muted, fontSize: 12)),
                        TextButton.icon(onPressed: () => _refresh(), icon: const Icon(Icons.refresh), label: const Text('Try again')),
                      ]),
                    ),
                  Container(
                    padding: const EdgeInsets.all(18),
                    decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(18), border: Border.all(color: _line)),
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      const Text('Booking journey', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w900, color: _ink)),
                      const SizedBox(height: 18),
                      _step('Booking placed', true, 'Your service request has been received.'),
                      _step('Professional assigned', assigned || started || completed,
                          assigned ? 'A professional has accepted your service.' : 'We are looking for an available professional.'),
                      _step('Service started', started, started ? 'Your professional has started the job.' : 'Updates when work begins.'),
                      _step('Service completed', completed, completed ? 'Your service is complete.' : 'Waiting for completion.'),
                    ]),
                  ),
                  const SizedBox(height: 16),
                  if (assigned)
                    Container(
                      padding: const EdgeInsets.all(18),
                      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(18), border: Border.all(color: _line)),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        const Text('Your professional', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w900, color: _ink)),
                        const SizedBox(height: 12),
                        Row(children: [
                          const CircleAvatar(backgroundColor: Color(0xFFEAF1EA), child: Icon(Icons.person_rounded, color: _green)),
                          const SizedBox(width: 12),
                          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text(_tracking['worker_name']?.toString() ?? 'Assigned professional',
                                style: const TextStyle(fontWeight: FontWeight.w800, color: _ink)),
                            if (_tracking['worker_rating'] != null)
                              Text('Rating: ${_tracking['worker_rating']}', style: const TextStyle(color: _muted, fontSize: 12)),
                          ])),

                        ]),
                        if ((_tracking['worker_phone']?.toString() ?? '').isNotEmpty)
                          SelectableText(_tracking['worker_phone'].toString(), style: const TextStyle(color: _muted)),
                      ]),
                    ),
                  const SizedBox(height: 16),
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(18), border: Border.all(color: _line)),
                    child: const Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Icon(Icons.location_searching_rounded, color: _green),
                      SizedBox(width: 10),
                      Expanded(child: Text(
                        'Live map and ETA will appear when the assigned professional shares verified GPS location. We will not display a guessed location.',
                        style: TextStyle(color: _muted, fontSize: 12, height: 1.45),
                      )),
                    ]),
                  ),
                  const SizedBox(height: 14),
                  if (!_terminal)
                    const Center(child: Text('Status refreshes automatically every 20 seconds',
                        style: TextStyle(color: _muted, fontSize: 11))),
                ],
              ),
            ),
    );
  }

  Widget _step(String title, bool complete, String detail) => Padding(
        padding: const EdgeInsets.only(bottom: 18),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(complete ? Icons.check_circle_rounded : Icons.radio_button_unchecked,
              color: complete ? _green : const Color(0xFFB9C2BB), size: 22),
          const SizedBox(width: 11),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: const TextStyle(fontWeight: FontWeight.w800, color: _ink)),
            const SizedBox(height: 3),
            Text(detail, style: const TextStyle(color: _muted, fontSize: 12, height: 1.35)),
          ])),
        ]),
      );
}
