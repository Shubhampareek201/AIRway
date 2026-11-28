import 'dart:async';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:airway/features/booking/data/booking_api.dart';
import 'package:airway/core/localization/airway_text.dart';

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

  Future<void> _openWorkerContact({required bool message}) async {
    final phone = _tracking['worker_phone']?.toString();
    if (_tracking['worker_contact_available'] != true || phone == null || phone.isEmpty) return;
    final uri = Uri(scheme: message ? 'sms' : 'tel', path: phone);
    final opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!opened && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Could not open the phone app.', 'फोन ऐप नहीं खुल सका।'))),
      );
    }
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
      case 'pending': return AirwayText.tr('Finding a professional', 'प्रोफ़ेशनल खोज रहे हैं');
      case 'confirmed': return AirwayText.tr('Booking confirmed', 'बुकिंग कन्फ़र्म हो गई');
      case 'assigned': return AirwayText.tr('Professional assigned', 'प्रोफ़ेशनल असाइन हो गया');
      case 'in_progress': return AirwayText.tr('Service in progress', 'सेवा जारी है');
      case 'completed': return AirwayText.tr('Service completed', 'सेवा पूरी हो गई');
      case 'cancelled': return AirwayText.tr('Booking cancelled', 'बुकिंग रद्द हो गई');
      case 'disputed': return AirwayText.tr('Booking under review', 'बुकिंग की समीक्षा हो रही है');
      default: return _status.replaceAll('_', ' ');
    }
  }

  @override
  Widget build(BuildContext context) {
    final assigned = _tracking['is_assigned'] == true;
    final workerLatitude = double.tryParse(_tracking['worker_latitude']?.toString() ?? '');
    final workerLongitude = double.tryParse(_tracking['worker_longitude']?.toString() ?? '');
    final locationIsFresh = _tracking['location_is_fresh'] == true &&
        workerLatitude != null && workerLongitude != null;
    final started = _status == 'in_progress' || _status == 'completed';
    final completed = _status == 'completed';
    final cancelled = _status == 'cancelled';
    return Scaffold(
      backgroundColor: const Color(0xFFF8FAF8),
      appBar: AppBar(
        backgroundColor: Colors.white,
        title: Text(AirwayText.tr('Track Service', 'सेवा ट्रैक करें')),
        actions: [
          IconButton(
            onPressed: _loading ? null : () => _refresh(),
            icon: const Icon(Icons.refresh_rounded),
            tooltip: AirwayText.tr('Refresh status', 'स्थिति रीफ़्रेश करें'),
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
                        Text(AirwayText.tr('Booking #${widget.bookingId}', 'बुकिंग #${widget.bookingId}'),
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
                        Text(AirwayText.tr('Could not refresh tracking', 'ट्रैकिंग रीफ़्रेश नहीं हो सकी'), style: TextStyle(fontWeight: FontWeight.w800, color: _ink)),
                        const SizedBox(height: 5),
                        Text(_error!, style: const TextStyle(color: _muted, fontSize: 12)),
                        TextButton.icon(onPressed: () => _refresh(), icon: const Icon(Icons.refresh), label: Text(AirwayText.tr('Try again', 'फिर कोशिश करें'))),
                      ]),
                    ),
                  Container(
                    padding: const EdgeInsets.all(18),
                    decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(18), border: Border.all(color: _line)),
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(AirwayText.tr('Booking journey', 'बुकिंग की प्रगति'), style: TextStyle(fontSize: 16, fontWeight: FontWeight.w900, color: _ink)),
                      const SizedBox(height: 18),
                      _step('Booking placed', true, 'Your service request has been received.'),
                      _step('Professional assigned', assigned || started || completed,
                          assigned ? 'A professional has accepted your service.' : 'We are looking for an available professional.'),
                      _step('Service started', started, started ? 'Your professional has started the job.' : 'Updates when work begins.'),
                      _step('Service completed', completed, completed ? 'Your service is complete.' : 'Waiting for completion.'),
                    ]),
                  ),
                  const SizedBox(height: 16),
                  if (locationIsFresh)
                    Container(
                      height: 238,
                      clipBehavior: Clip.antiAlias,
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(18),
                        border: Border.all(color: _line),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Padding(
                            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
                            child: Row(
                              children: [
                                const Icon(Icons.my_location_rounded, color: _green, size: 18),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    AirwayText.tr('Professional live location', 'प्रोफ़ेशनल की लाइव लोकेशन'),
                                    style: const TextStyle(fontWeight: FontWeight.w800, color: _ink),
                                  ),
                                ),
                                const Text('LIVE', style: TextStyle(color: _green, fontSize: 10, fontWeight: FontWeight.w900)),
                              ],
                            ),
                          ),
                          Expanded(
                            child: FlutterMap(
                              options: MapOptions(
                                initialCenter: LatLng(workerLatitude!, workerLongitude!),
                                initialZoom: 15,
                                interactionOptions: const InteractionOptions(
                                  flags: InteractiveFlag.all & ~InteractiveFlag.rotate,
                                ),
                              ),
                              children: [
                                TileLayer(
                                  urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                                  userAgentPackageName: 'com.airwayservices.airway',
                                ),
                                MarkerLayer(
                                  markers: [
                                    Marker(
                                      point: LatLng(workerLatitude, workerLongitude),
                                      width: 46,
                                      height: 46,
                                      child: const Icon(Icons.location_on_rounded, color: _green, size: 42),
                                    ),
                                  ],
                                ),
                                RichAttributionWidget(
                                  attributions: [
                                    TextSourceAttribution('© OpenStreetMap contributors'),
                                  ],
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  if (!locationIsFresh && assigned)
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(18), border: Border.all(color: _line)),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Icon(Icons.location_searching_rounded, color: _green),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              AirwayText.tr(
                                (_tracking['location_unavailable_reason']?.toString().trim().isNotEmpty ?? false)
                                    ? _tracking['location_unavailable_reason'].toString()
                                    : 'Live location is not available right now. Your booking status will continue to update automatically.',
                                'लाइव लोकेशन अभी उपलब्ध नहीं है। आपकी बुकिंग की स्थिति अपने आप अपडेट होती रहेगी।',
                              ),
                              style: const TextStyle(color: _muted, fontSize: 12, height: 1.45),
                            ),
                          ),
                        ],
                      ),
                    ),
                  if (assigned)
                    Container(
                      padding: const EdgeInsets.all(18),
                      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(18), border: Border.all(color: _line)),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(AirwayText.tr('Your professional', 'आपके प्रोफ़ेशनल'), style: TextStyle(fontSize: 16, fontWeight: FontWeight.w900, color: _ink)),
                        const SizedBox(height: 12),
                        if (_tracking['worker_unavailable'] == true)
                          Padding(
                            padding: const EdgeInsets.only(bottom: 10),
                            child: Text(
                              AirwayText.tr('This professional is temporarily unavailable. AIRway operations is reviewing your booking.', 'यह प्रोफ़ेशनल अभी उपलब्ध नहीं है। AIRway टीम आपकी बुकिंग की समीक्षा कर रही है।'),
                              style: TextStyle(color: _muted, fontSize: 12, height: 1.4),
                            ),
                          ),
                        Row(children: [
                          CircleAvatar(
                            radius: 28,
                            backgroundColor: const Color(0xFFEAF1EA),
                            backgroundImage: (_tracking['worker_photo']?.toString().isNotEmpty ?? false)
                                ? NetworkImage(_tracking['worker_photo'].toString())
                                : null,
                            child: (_tracking['worker_photo']?.toString().isNotEmpty ?? false)
                                ? null
                                : const Icon(Icons.person_rounded, color: _green),
                          ),
                          const SizedBox(width: 12),
                          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text(_tracking['worker_name']?.toString() ?? AirwayText.tr('Assigned professional', 'असाइन किया गया प्रोफ़ेशनल'),
                                style: const TextStyle(fontWeight: FontWeight.w800, color: _ink)),
                            if (_tracking['worker_rating'] != null)
                              Text(AirwayText.tr('★ ${_tracking['worker_rating']} (${_tracking['worker_rating_count'] ?? 0} ratings)', '★ ${_tracking['worker_rating']} (${_tracking['worker_rating_count'] ?? 0} रेटिंग)'),
                                  style: const TextStyle(color: _muted, fontSize: 12)),
                            if ((_tracking['worker_experience_years'] ?? 0) > 0)
                              Text(AirwayText.tr('${_tracking['worker_experience_years']} years experience', '${_tracking['worker_experience_years']} साल का अनुभव'),
                                  style: const TextStyle(color: _muted, fontSize: 12)),
                          ])),
                        ]),
                        if ((_tracking['worker_qualification']?.toString() ?? '').isNotEmpty)
                          Padding(
                            padding: const EdgeInsets.only(top: 10),
                            child: Text(AirwayText.tr('Qualification: ${_tracking['worker_qualification']}', 'योग्यता: ${_tracking['worker_qualification']}'),
                                style: const TextStyle(color: _muted, fontSize: 12)),
                          ),
                        if ((_tracking['worker_bio']?.toString() ?? '').isNotEmpty)
                          Padding(
                            padding: const EdgeInsets.only(top: 8),
                            child: Text(_tracking['worker_bio'].toString(),
                                style: const TextStyle(color: _muted, fontSize: 12, height: 1.4)),
                          ),
                        if ((_tracking['worker_completed_jobs'] ?? 0) > 0)
                          Padding(
                            padding: const EdgeInsets.only(top: 8),
                            child: Text(AirwayText.tr('${_tracking['worker_completed_jobs']} completed AIRway jobs', 'AIRway पर ${_tracking['worker_completed_jobs']} काम पूरे किए'),
                                style: const TextStyle(color: _muted, fontSize: 12)),
                          ),
                        for (final service in (_tracking['worker_verified_services'] as List? ?? const []))
                          Padding(
                            padding: const EdgeInsets.only(top: 10),
                            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              Text(service['service']?.toString() ?? '',
                                  style: const TextStyle(fontWeight: FontWeight.w700, color: _ink)),
                              if ((service['verified_skills'] as List? ?? const []).isNotEmpty)
                                Text(AirwayText.tr('Verified skills: ${(service['verified_skills'] as List).join(', ')}', 'वेरिफ़ाइड कौशल: ${(service['verified_skills'] as List).join(', ')}'),
                                    style: const TextStyle(color: _muted, fontSize: 12)),
                            ]),
                          ),
                        if (_tracking['worker_contact_available'] == true && (_tracking['worker_phone']?.toString().isNotEmpty ?? false))
                          Padding(
                            padding: const EdgeInsets.only(top: 12),
                            child: Wrap(spacing: 10, children: [
                              OutlinedButton.icon(
                                onPressed: () => _openWorkerContact(message: false),
                                icon: const Icon(Icons.call_rounded),
                                label: Text(AirwayText.tr('Call professional', 'प्रोफ़ेशनल को कॉल करें')),
                              ),
                              OutlinedButton.icon(
                                onPressed: () => _openWorkerContact(message: true),
                                icon: const Icon(Icons.sms_rounded),
                                label: Text(AirwayText.tr('SMS', 'SMS')),
                              ),
                            ]),
                          )
                        else if (_tracking['worker_contact_available_at'] != null)
                          Padding(
                            padding: const EdgeInsets.only(top: 12),
                            child: Text(
                              AirwayText.tr('Call and SMS unlock one hour before your appointment: ${_tracking['worker_contact_available_at']}', 'कॉल और SMS अपॉइंटमेंट से एक घंटे पहले उपलब्ध होंगे।'),
                              style: TextStyle(color: _muted, fontSize: 11, height: 1.4),
                            ),
                          )
                        else
                          Padding(
                            padding: const EdgeInsets.only(top: 12),
                            child: Text(AirwayText.tr('Your contact details stay private. Contact AIRway Support if you need help.', 'आपकी संपर्क जानकारी निजी रहती है। मदद के लिए AIRway सपोर्ट से संपर्क करें।'),
                                style: TextStyle(color: _muted, fontSize: 11, height: 1.4)),
                          ),
                      ]),
                    ),
                  const SizedBox(height: 16),
                  const SizedBox(height: 14),
                  if (!_terminal)
                    Center(child: Text(AirwayText.tr('Status refreshes automatically every 20 seconds', 'स्थिति हर 20 सेकंड में अपने आप अपडेट होती है'),
                        style: TextStyle(color: _muted, fontSize: 11))),
                ],
              ),
            ),
    );
  }

  Widget _step(String title, bool complete, String detail) {
    final titleHindi = switch (title) {
      'Booking placed' => 'बुकिंग की गई',
      'Professional assigned' => 'प्रोफ़ेशनल असाइन हुआ',
      'Service started' => 'सेवा शुरू हुई',
      'Service completed' => 'सेवा पूरी हुई',
      _ => title,
    };
    final detailHindi = switch (detail) {
      'Your service request has been received.' => 'आपकी सेवा रिक्वेस्ट मिल गई है।',
      'A professional has accepted your service.' => 'एक प्रोफ़ेशनल ने आपकी सेवा स्वीकार कर ली है।',
      'We are looking for an available professional.' => 'हम उपलब्ध प्रोफ़ेशनल खोज रहे हैं।',
      'Your professional has started the job.' => 'आपके प्रोफ़ेशनल ने काम शुरू कर दिया है।',
      'Updates when work begins.' => 'काम शुरू होने पर अपडेट मिलेगा।',
      'Your service is complete.' => 'आपकी सेवा पूरी हो गई है।',
      'Waiting for completion.' => 'सेवा पूरी होने की प्रतीक्षा है।',
      _ => detail,
    };
    return Padding(
      padding: const EdgeInsets.only(bottom: 18),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(complete ? Icons.check_circle_rounded : Icons.radio_button_unchecked,
            color: complete ? _green : const Color(0xFFB9C2BB), size: 22),
        const SizedBox(width: 11),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(AirwayText.tr(title, titleHindi), style: const TextStyle(fontWeight: FontWeight.w800, color: _ink)),
          const SizedBox(height: 3),
          Text(AirwayText.tr(detail, detailHindi), style: const TextStyle(color: _muted, fontSize: 12, height: 1.35)),
        ])),
      ]),
    );
  }
}
