import 'dart:async';

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:airway/core/navigation/airway_navigator.dart';
import 'package:airway/features/worker/data/worker_api.dart';
import 'package:airway/features/worker/data/worker_models.dart';

class WorkerOfferAlertListener extends StatefulWidget {
  const WorkerOfferAlertListener({super.key, required this.child});

  final Widget child;

  @override
  State<WorkerOfferAlertListener> createState() => _WorkerOfferAlertListenerState();
}

class _WorkerOfferAlertListenerState extends State<WorkerOfferAlertListener> {
  StreamSubscription<RemoteMessage>? _subscription;
  final List<int> _queuedOfferIds = [];
  final Set<int> _queuedOrShown = {};
  bool _showing = false;

  @override
  void initState() {
    super.initState();
    _subscription = FirebaseMessaging.onMessage.listen(_onForegroundMessage);
  }

  @override
  void dispose() {
    _subscription?.cancel();
    super.dispose();
  }

  void _onForegroundMessage(RemoteMessage message) {
    if (message.data['notification_kind'] != 'worker_offer') return;
    final offerId = int.tryParse(message.data['offer_id']?.toString() ?? '');
    if (offerId == null || !_queuedOrShown.add(offerId)) return;
    _queuedOfferIds.add(offerId);
    unawaited(_showNextOffer());
  }

  Future<void> _showNextOffer() async {
    if (_showing) return;
    _showing = true;
    try {
      while (_queuedOfferIds.isNotEmpty) {
        final offerId = _queuedOfferIds.removeAt(0);
        try {
          final offers = await WorkerApi.getJobOffers();
          WorkerOffer? offer;
          for (final candidate in offers) {
            if (candidate.id == offerId) {
              offer = candidate;
              break;
            }
          }
          if (offer == null ||
              offer.status != WorkerOffer.pending ||
              offer.expiresAt == null ||
              !offer.expiresAt!.isAfter(DateTime.now())) {
            continue;
          }

          final navigatorContext = airwayNavigatorKey.currentContext;
          if (navigatorContext == null) continue;
          await showDialog<void>(
            context: navigatorContext,
            useRootNavigator: true,
            barrierDismissible: false,
            builder: (_) => _IncomingWorkerOfferDialog(
              offer: offer!,
              onAccept: () => WorkerApi.acceptOffer(offerId),
              onDecline: () => WorkerApi.declineOffer(offerId),
            ),
          );
        } catch (_) {
          // The offers page continues polling and exposes a retry path if the
          // network is unavailable. Do not let an alert failure crash the app.
        }
      }
    } finally {
      _showing = false;
    }
  }

  @override
  Widget build(BuildContext context) => widget.child;
}

class _IncomingWorkerOfferDialog extends StatefulWidget {
  const _IncomingWorkerOfferDialog({
    required this.offer,
    required this.onAccept,
    required this.onDecline,
  });

  final WorkerOffer offer;
  final Future<void> Function() onAccept;
  final Future<void> Function() onDecline;

  @override
  State<_IncomingWorkerOfferDialog> createState() =>
      _IncomingWorkerOfferDialogState();
}

class _IncomingWorkerOfferDialogState
    extends State<_IncomingWorkerOfferDialog> {
  Timer? _ringTimer;
  Timer? _countdownTimer;
  bool _busy = false;
  String? _error;
  DateTime _now = DateTime.now();

  @override
  void initState() {
    super.initState();
    _ring();
    _ringTimer = Timer.periodic(const Duration(seconds: 2), (_) => _ring());
    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) return;
      setState(() => _now = DateTime.now());
      if (_remaining.inSeconds <= 0) {
        Navigator.of(context, rootNavigator: true).pop();
      }
    });
  }

  Duration get _remaining =>
      (widget.offer.expiresAt?.toLocal() ?? _now).difference(_now);

  void _ring() {
    if (mounted && !_busy && _remaining.inSeconds > 0) {
      unawaited(SystemSound.play(SystemSoundType.alert));
    }
  }

  @override
  void dispose() {
    _ringTimer?.cancel();
    _countdownTimer?.cancel();
    super.dispose();
  }

  String get _countdown {
    final seconds = _remaining.inSeconds;
    if (seconds <= 0) return 'Service time reached';
    final days = seconds ~/ 86400;
    final hours = (seconds % 86400) ~/ 3600;
    final minutes = (seconds % 3600) ~/ 60;
    final secs = seconds % 60;
    if (days > 0) return '${days}d ${hours}h remaining';
    return '${hours.toString().padLeft(2, '0')}:${minutes.toString().padLeft(2, '0')}:${secs.toString().padLeft(2, '0')} remaining';
  }

  Future<void> _respond(bool accept) async {
    if (_busy || _remaining.inSeconds <= 0) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (accept) {
        await widget.onAccept();
      } else {
        await widget.onDecline();
      }
      if (mounted) Navigator.of(context, rootNavigator: true).pop();
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.toString().replaceFirst('Exception: ', '');
        _busy = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final offer = widget.offer;
    final expired = _remaining.inSeconds <= 0;
    return PopScope(
      canPop: false,
      child: AlertDialog(
        title: const Row(
          children: [
            Icon(Icons.notifications_active_rounded, color: Color(0xFFB45309)),
            SizedBox(width: 9),
            Expanded(child: Text('New AIRway job offer')),
          ],
        ),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                offer.serviceTitle ?? 'New service request',
                style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800),
              ),
              if ((offer.customerName ?? '').isNotEmpty) ...[
                const SizedBox(height: 8),
                Text('Customer: ${offer.customerName}'),
              ],
              if (offer.scheduledAt != null) ...[
                const SizedBox(height: 6),
                Text('Service: ${offer.scheduledAt!.toLocal()}'),
              ],
              if ((offer.serviceAddress ?? '').isNotEmpty) ...[
                const SizedBox(height: 6),
                Text('Address: ${offer.serviceAddress}'),
              ],
              if ((offer.bookingNotes ?? '').isNotEmpty) ...[
                const SizedBox(height: 6),
                Text('Customer message: ${offer.bookingNotes}'),
              ],
              const SizedBox(height: 12),
              Text(
                offer.workerPayout == null
                    ? 'Your payout is not configured yet'
                    : 'Your payout: ₹${offer.workerPayout!.toStringAsFixed(2)}',
                style: const TextStyle(
                  color: Color(0xFF176B3A),
                  fontWeight: FontWeight.w800,
                  fontSize: 16,
                ),
              ),
              const SizedBox(height: 10),
              Text(
                _countdown,
                style: const TextStyle(fontWeight: FontWeight.w800),
              ),
              if (_error != null) ...[
                const SizedBox(height: 10),
                Text(_error!, style: const TextStyle(color: Colors.red)),
              ],
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: _busy || expired ? null : () => _respond(false),
            child: const Text('Reject'),
          ),
          FilledButton(
            onPressed: _busy || expired ? null : () => _respond(true),
            child: _busy
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('Accept'),
          ),
        ],
      ),
    );
  }
}
