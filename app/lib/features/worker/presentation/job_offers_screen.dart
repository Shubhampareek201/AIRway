import 'dart:async';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/worker/data/worker_models.dart';
import 'package:airway/features/worker/data/worker_api.dart';
import 'package:airway/core/localization/airway_text.dart';

class JobOffersScreen extends StatefulWidget {
  const JobOffersScreen({super.key});

  @override
  State<JobOffersScreen> createState() => _JobOffersScreenState();
}

class _JobOffersScreenState extends State<JobOffersScreen> with WidgetsBindingObserver {
  List<WorkerOffer> _offers = [];
  bool _loading = true;
  String? _error;
  int _actionInProgress = -1;
  Timer? _pollTimer;
  bool _fetching = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _loadOffers();
    // Keep this route current even when it was already open before a customer
    // completed checkout. The dashboard's polling does not refresh this page.
    _pollTimer = Timer.periodic(const Duration(seconds: 10), (_) {
      if (mounted && WidgetsBinding.instance.lifecycleState == AppLifecycleState.resumed) {
        _loadOffers(showLoader: false);
      }
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _loadOffers(showLoader: false);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _loadOffers({bool showLoader = true}) async {
    if (_fetching) return;
    _fetching = true;
    if (mounted) {
      setState(() {
        if (showLoader) _loading = true;
        _error = null;
      });
    }
    try {
      final offers = await WorkerApi.getJobOffers();
      if (mounted) {
        setState(() {
          _offers = offers;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = '${AirwayText.tr('Could not load job offers.', 'जॉब ऑफ़र लोड नहीं हो सके।')}\n${e.toString().replaceFirst('Exception: ', '')}';
        });
      }
    } finally {
      _fetching = false;
      if (mounted && showLoader) setState(() { _loading = false; });
    }
  }

  Future<void> _refresh() async {
    await _loadOffers();
  }

  Future<void> _acceptOffer(int offerId) async {
    setState(() => _actionInProgress = offerId);
    try {
      await WorkerApi.acceptOffer(offerId);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(AirwayText.tr('Offer accepted!', 'ऑफ़र स्वीकार कर लिया गया!'))),
        );
        _loadOffers();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(AirwayText.tr('Failed to accept: $e', 'ऑफ़र स्वीकार नहीं हुआ: $e'))),
        );
      }
    } finally {
      if (mounted) setState(() => _actionInProgress = -1);
    }
  }

  Future<void> _declineOffer(int offerId) async {
    setState(() => _actionInProgress = offerId);
    try {
      await WorkerApi.declineOffer(offerId);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(AirwayText.tr('Offer declined', 'ऑफ़र अस्वीकार कर दिया गया'))),
        );
        _loadOffers();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(AirwayText.tr('Failed to decline: $e', 'ऑफ़र अस्वीकार नहीं हुआ: $e'))),
        );
      }
    } finally {
      if (mounted) setState(() => _actionInProgress = -1);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(AirwayText.tr('Job Offers', 'जॉब ऑफ़र')),
      ),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: _buildBody(),
      ),
    );
  }

  Widget _buildBody() {
    if (_loading) return const Center(child: CircularProgressIndicator());

    if (_error != null) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(24),
        children: [
          const SizedBox(height: 70),
          const Icon(Icons.cloud_off_rounded, size: 48, color: AirwayColors.error),
          const SizedBox(height: 16),
          Text(_error!, textAlign: TextAlign.center),
          const SizedBox(height: 16),
          Center(child: FilledButton.icon(onPressed: _refresh, icon: const Icon(Icons.refresh), label: Text(AirwayText.tr('Retry', 'फिर कोशिश करें')))),
        ],
      );
    }

    final pendingOffers = _offers.where((o) => o.status == WorkerOffer.pending).toList();
    final acceptedOffers = _offers.where((o) => o.status == WorkerOffer.accepted).toList();
    final otherOffers = _offers.where((o) => [WorkerOffer.declined, WorkerOffer.expired, WorkerOffer.withdrawn].contains(o.status)).toList();

    if (_offers.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(24),
        children: [
          const SizedBox(height: 55),
          Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(color: AirwayColors.primary.withValues(alpha: 0.07), borderRadius: BorderRadius.circular(22)),
            child: Column(
              children: [
                const Icon(Icons.inbox_rounded, size: 52, color: AirwayColors.primary),
                const SizedBox(height: 14),
                Text(AirwayText.tr('No service requests yet', 'अभी कोई सर्विस रिक्वेस्ट नहीं है'), style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900), textAlign: TextAlign.center),
                const SizedBox(height: 8),
                Text(AirwayText.tr('New requests for the services you provide will appear here. Keep your availability on and pull down to refresh.', 'आपकी सेवाओं की नई रिक्वेस्ट यहाँ दिखेंगी। उपलब्धता ऑनलाइन रखें और रीफ़्रेश करने के लिए नीचे खींचें।'), textAlign: TextAlign.center, style: TextStyle(color: AirwayColors.textSecondary, height: 1.4)),
              ],
            ),
          ),
        ],
      );
    }

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
      children: [
        if (pendingOffers.isNotEmpty) ...[
          Row(
            children: [
              Expanded(child: Text(AirwayText.tr('Needs your response', 'आपके जवाब का इंतज़ार'), style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w900))),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                decoration: BoxDecoration(color: AirwayColors.primary.withValues(alpha: 0.10), borderRadius: BorderRadius.circular(20)),
                child: Text('${pendingOffers.length} NEW', style: const TextStyle(color: AirwayColors.primary, fontSize: 11, fontWeight: FontWeight.w900)),
              ),
            ],
          ),
          const SizedBox(height: 10),
          ...pendingOffers.map((o) => _buildOfferCard(o, isAccepted: false)),
        ],
        if (acceptedOffers.isNotEmpty) ...[
          const SizedBox(height: 14),
          Text(AirwayText.tr('Accepted requests', 'स्वीकृत रिक्वेस्ट'), style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w900)),
          const SizedBox(height: 10),
          ...acceptedOffers.map((o) => _buildOfferCard(o, isAccepted: true)),
        ],
        if (otherOffers.isNotEmpty) ...[
          const SizedBox(height: 14),
          Text(AirwayText.tr('Past requests', 'पुरानी रिक्वेस्ट'), style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w900)),
          const SizedBox(height: 10),
          ...otherOffers.take(5).map((o) => _buildOfferCard(o, isAccepted: false)),
        ],
      ],
    );
  }

  Widget _buildOfferCard(WorkerOffer offer, {required bool isAccepted}) {
    final inProgress = _actionInProgress == offer.id;
    final pending = offer.status == WorkerOffer.pending;
    final serviceName = offer.serviceTitle?.trim().isNotEmpty == true
        ? offer.serviceTitle!.trim()
        : 'AIRway service';
    final address = offer.serviceAddress?.trim() ?? '';
    final statusLabel = switch (offer.status) {
      WorkerOffer.accepted => AirwayText.tr('Accepted', 'स्वीकृत'),
      WorkerOffer.declined => AirwayText.tr('Declined', 'अस्वीकृत'),
      WorkerOffer.expired => AirwayText.tr('Expired', 'समय समाप्त'),
      WorkerOffer.withdrawn => AirwayText.tr('No longer available', 'अब उपलब्ध नहीं'),
      _ => AirwayText.tr('New request', 'नई रिक्वेस्ट'),
    };

    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: pending ? AirwayColors.primary.withValues(alpha: 0.28) : const Color(0xFFE8E2F5)),
        boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.035), blurRadius: 12, offset: const Offset(0, 4))],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (offer.serviceImageUrl?.isNotEmpty == true)
            ClipRRect(
              borderRadius: BorderRadius.circular(14),
              child: Image.network(
                offer.serviceImageUrl!,
                width: double.infinity,
                height: 150,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => const SizedBox.shrink(),
              ),
            ),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 46,
                height: 46,
                decoration: BoxDecoration(color: AirwayColors.primary.withValues(alpha: 0.10), borderRadius: BorderRadius.circular(14)),
                child: const Icon(Icons.home_repair_service_rounded, color: AirwayColors.primary, size: 25),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(serviceName, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w900)),
                    const SizedBox(height: 3),
                    Text('Booking #${offer.bookingId}', style: TextStyle(fontSize: 12, color: AirwayColors.textSecondary)),
                    if (offer.variantTitle?.trim().isNotEmpty == true)
                      Padding(padding: const EdgeInsets.only(top: 3), child: Text(offer.variantTitle!, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700))),
                  ],
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
                decoration: BoxDecoration(
                  color: pending ? const Color(0xFFEAF7EF) : const Color(0xFFF1EFF7),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(statusLabel, style: TextStyle(color: pending ? const Color(0xFF21834A) : AirwayColors.textSecondary, fontSize: 10, fontWeight: FontWeight.w800)),
              ),
            ],
          ),
          const SizedBox(height: 14),
          if (offer.customerName?.trim().isNotEmpty == true)
            _infoLine(Icons.person_outline_rounded, 'Customer: ${offer.customerName}'),
          const SizedBox(height: 8),
          _infoLine(Icons.calendar_month_outlined, offer.scheduledAt == null ? 'Schedule to be confirmed' : 'Service time: ${_formatDateTime(offer.scheduledAt!)}'),
          if (address.isNotEmpty) ...[
            const SizedBox(height: 8),
            _infoLine(Icons.location_on_outlined, address, maxLines: 3),
            if (offer.addressLatitude != null && offer.addressLongitude != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: OutlinedButton.icon(
                  onPressed: () => _openMap(offer),
                  icon: const Icon(Icons.directions_rounded),
                  label: Text(AirwayText.tr('Open customer location in Maps', 'ग्राहक की लोकेशन Maps में खोलें')),
                ),
              ),
          ],
          if (offer.serviceDescription?.trim().isNotEmpty == true) ...[
            const SizedBox(height: 12),
            Text(AirwayText.tr('What you need to do', 'आपको क्या काम करना है'), style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 14)),
            const SizedBox(height: 5),
            Text(offer.serviceDescription!, style: const TextStyle(fontSize: 13, height: 1.45)),
          ],
          if (offer.customerIssuePhotoUrl?.isNotEmpty == true) ...[
            const SizedBox(height: 12),
            Text(AirwayText.tr('Customer reference photo', 'ग्राहक की भेजी फोटो'), style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 13)),
            const SizedBox(height: 6),
            ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: Image.network(
                offer.customerIssuePhotoUrl!,
                width: double.infinity,
                height: 180,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => Text(AirwayText.tr('Photo could not be loaded.', 'फोटो लोड नहीं हो सकी।')),
              ),
            ),
          ],
          const SizedBox(height: 8),
          Container(
            width: double.infinity,
            margin: const EdgeInsets.only(top: 12),
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: const Color(0xFFEAF7EF),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(AirwayText.tr('YOUR EARNING AFTER COMPLETION', 'काम पूरा होने पर आपकी कमाई'), style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w900, color: Color(0xFF267747), letterSpacing: 0.4)),
                const SizedBox(height: 3),
                Text(offer.workerPayout == null ? AirwayText.tr('Not configured yet', 'अभी तय नहीं है') : '₹${offer.workerPayout!.toStringAsFixed(2)}', style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w900, color: Color(0xFF176B3A))),
                if (offer.workerPayout == null)
                  Text(AirwayText.tr('AIRway finance must set your commission before a fixed payout can be shown.', 'फिक्स कमाई दिखाने के लिए AIRway finance को आपका कमीशन सेट करना होगा।'), style: const TextStyle(fontSize: 11, color: Color(0xFF5D6F62))),
              ],
            ),
          ),
          const SizedBox(height: 8),
          _infoLine(Icons.timer_outlined, 'Estimated duration: ${offer.expectedDurationMinutes} minutes'),
          if (offer.quantity > 1) ...[
            const SizedBox(height: 8),
            _infoLine(Icons.format_list_numbered_rounded, 'Quantity: ${offer.quantity}'),
          ],
          if (offer.orderServices.length > 1) ...[
            const SizedBox(height: 10),
            Text(AirwayText.tr('Services in this appointment', 'इस अपॉइंटमेंट की सेवाएँ'), style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w800)),
            const SizedBox(height: 4),
            ...offer.orderServices.map((service) => Padding(
              padding: const EdgeInsets.only(bottom: 3),
              child: Text('• ${service['service_title'] ?? 'Service'}${service['variant_title'] == null ? '' : ' — ${service['variant_title']}'}', style: TextStyle(fontSize: 12, color: AirwayColors.textSecondary)),
            )),
          ],
          if (offer.bookingNotes?.trim().isNotEmpty == true) ...[
            const SizedBox(height: 10),
            _infoLine(Icons.notes_rounded, 'Customer instructions: ${offer.bookingNotes}', maxLines: 4),
          ],
          if (offer.customerAnswers.isNotEmpty || offer.formResponses.isNotEmpty || offer.addons.isNotEmpty) ...[
            const SizedBox(height: 10),
            ExpansionTile(
              tilePadding: EdgeInsets.zero,
              childrenPadding: const EdgeInsets.only(bottom: 8),
              title: Text(AirwayText.tr('Service details & customer answers', 'सेवा विवरण और ग्राहक के जवाब'), style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w800)),
              children: [
                for (final entry in offer.customerAnswers.entries)
                  Align(alignment: Alignment.centerLeft, child: Padding(padding: const EdgeInsets.only(bottom: 5), child: Text(workerCustomerAnswerLabel(entry.key, entry.value), style: const TextStyle(fontSize: 12)))),
                for (final answer in offer.formResponses)
                  Align(alignment: Alignment.centerLeft, child: Padding(padding: const EdgeInsets.only(bottom: 5), child: Text('${answer['label'] ?? answer['key']}: ${answer['value']}', style: const TextStyle(fontSize: 12)))),
                if (offer.addons.isNotEmpty)
                  Align(alignment: Alignment.centerLeft, child: Text('Add-ons: ${offer.addons.map((addon) => addon['title']).join(', ')}', style: const TextStyle(fontSize: 12))),
              ],
            ),
          ],
          if (offer.status == WorkerOffer.accepted)
            Padding(padding: const EdgeInsets.only(top: 10), child: Text(AirwayText.tr('You accepted this request. Open Assigned Jobs to continue.', 'आपने यह रिक्वेस्ट स्वीकार की है। आगे बढ़ने के लिए Assigned Jobs खोलें।'), style: const TextStyle(color: AirwayColors.success, fontSize: 12, fontWeight: FontWeight.w700))),
          if (pending) ...[
            const SizedBox(height: 14),
            if (inProgress)
              const Center(child: CircularProgressIndicator())
            else
              Row(
                children: [
                  if (offer.canDecline)
                    Expanded(child: OutlinedButton(
                      onPressed: () => _declineOffer(offer.id),
                      style: OutlinedButton.styleFrom(foregroundColor: AirwayColors.error, side: const BorderSide(color: AirwayColors.error), minimumSize: const Size.fromHeight(48)),
                      child: Text(AirwayText.tr('Decline', 'मना करें')),
                    )),
                  if (offer.canDecline && offer.canAccept) const SizedBox(width: 10),
                  if (offer.canAccept)
                    Expanded(flex: 2, child: FilledButton.icon(
                      onPressed: () => _acceptOffer(offer.id),
                      icon: const Icon(Icons.check_circle_outline_rounded),
                      label: Text(AirwayText.tr('Accept request', 'रिक्वेस्ट स्वीकार करें')),
                      style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(48)),
                    )),
                ],
              ),
          ],
        ],
      ),
    );
  }

  Future<void> _openMap(WorkerOffer offer) async {
    final latitude = offer.addressLatitude;
    final longitude = offer.addressLongitude;
    if (latitude == null || longitude == null) return;
    final uri = Uri.parse('https://www.google.com/maps/search/?api=1&query=$latitude,$longitude');
    final opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!opened && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Could not open Maps on this device.', 'इस डिवाइस पर Maps नहीं खुल सका।'))),
      );
    }
  }

  Widget _infoLine(IconData icon, String value, {int maxLines = 1}) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 17, color: AirwayColors.primary),
        const SizedBox(width: 8),
        Expanded(child: Text(value, maxLines: maxLines, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 12, color: AirwayColors.textSecondary, height: 1.35))),
      ],
    );
  }

  Widget _buildActionButtons(WorkerOffer offer, bool inProgress, bool isAccepted) {
    final status = offer.status;

    // Accepted offers show status only
    if (status == WorkerOffer.accepted) {
      return Chip(
        label: Text(AirwayText.tr('Accepted', 'स्वीकृत'), style: TextStyle(fontSize: 12)),
        backgroundColor: Colors.green.shade100,
      );
    }

    // Declined offers show status
    if (status == WorkerOffer.declined) {
      return Chip(
        label: Text(AirwayText.tr('Declined', 'अस्वीकृत')),
        backgroundColor: Colors.red.shade100,
      );
    }

    // Expired offers show status
    if (status == WorkerOffer.expired) {
      return Chip(
        label: Text(AirwayText.tr('Expired', 'समाप्त')),
        backgroundColor: Colors.grey.shade200,
      );
    }

    // Withdrawn offers show status
    if (status == WorkerOffer.withdrawn) {
      return Chip(
        label: Text(AirwayText.tr('Withdrawn', 'वापस लिया गया')),
        backgroundColor: Colors.grey.shade200,
      );
    }

    // Pending offers - show action buttons
    if (status == WorkerOffer.pending) {
      if (inProgress) {
        return const SizedBox(
          width: 24,
          height: 24,
          child: CircularProgressIndicator(strokeWidth: 2),
        );
      }

      return Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (offer.canDecline)
            OutlinedButton(
              onPressed: () => _declineOffer(offer.id),
              style: OutlinedButton.styleFrom(
                foregroundColor: AirwayColors.error,
                side: const BorderSide(color: AirwayColors.error),
              ),
              child: Text(AirwayText.tr('Decline', 'अस्वीकार करें')),
            ),
          const SizedBox(width: 8),
          if (offer.canAccept)
            FilledButton(
              onPressed: () => _acceptOffer(offer.id),
              child: Text(AirwayText.tr('Accept', 'स्वीकार करें')),
            ),
        ],
      );
    }

    // Unknown status - no action
    return const SizedBox.shrink();
  }

  String _formatDateTime(DateTime dt) {
    final h = dt.hour.toString().padLeft(2, '0');
    final m = dt.minute.toString().padLeft(2, '0');
    final d = dt.day.toString();
    final mo = dt.month.toString().padLeft(2, '0');
    return '$d/$mo/${dt.year} $h:$m';
  }
}