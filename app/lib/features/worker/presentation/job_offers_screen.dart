import 'dart:async';
import 'package:flutter/material.dart';

import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/worker/data/worker_models.dart';
import 'package:airway/features/worker/data/worker_api.dart';

class JobOffersScreen extends StatefulWidget {
  const JobOffersScreen({super.key});

  @override
  State<JobOffersScreen> createState() => _JobOffersScreenState();
}

class _JobOffersScreenState extends State<JobOffersScreen> {
  List<WorkerOffer> _offers = [];
  bool _loading = true;
  String? _error;
  int _actionInProgress = -1;
  Timer? _activeTimer;
  final Map<int, Duration> _timeRemaining = {};

  @override
  void initState() {
    super.initState();
    _loadOffers();
  }

  @override
  void dispose() {
    _activeTimer?.cancel();
    super.dispose();
  }

  Future<void> _loadOffers() async {
    if (mounted) setState(() { _loading = true; _error = null; });
    try {
      final offers = await WorkerApi.getJobOffers();
      if (mounted) {
        setState(() {
          _offers = offers;
          _timeRemaining.clear();
          // Set up countdown timers for each pending offer
          for (final offer in offers.where((o) => o.status == WorkerOffer.pending && o.expiresAt != null)) {
            final remaining = offer.expiresAt!.difference(DateTime.now());
            if (remaining.inSeconds > 0) {
              _timeRemaining[offer.id] = remaining;
            }
          }
          // Start the timer for countdown updates
          _startCountdownTimer();
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = 'Could not load job offers.';
        });
      }
    } finally {
      if (mounted) setState(() { _loading = false; });
    }
  }

  void _startCountdownTimer() {
    _activeTimer?.cancel();
    _activeTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) return;
      bool needsUpdate = false;
      final toRemove = <int>[];

      for (final entry in _timeRemaining.entries.toList()) {
        final remaining = entry.value - const Duration(seconds: 1);
        if (remaining.inSeconds <= 0) {
          toRemove.add(entry.key);
          needsUpdate = true;
        } else {
          _timeRemaining[entry.key] = remaining;
        }
      }

      if (needsUpdate) {
        setState(() {
          for (final id in toRemove) {
            _timeRemaining.remove(id);
          }
        });
        // Reload offers to refresh expired ones
        _loadOffers();
      }
    });
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
          const SnackBar(content: Text('Offer accepted!')),
        );
        _loadOffers();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to accept: $e')),
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
          const SnackBar(content: Text('Offer declined')),
        );
        _loadOffers();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to decline: $e')),
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
        title: const Text('Job Offers'),
      ),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: _buildBody(),
      ),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_error != null) {
      return SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.error_outline, size: 48, color: AirwayColors.error),
                const SizedBox(height: 16),
                Text(_error!),
                const SizedBox(height: 16),
                FilledButton(onPressed: _refresh, child: const Text('Retry')),
              ],
            ),
          ),
        ),
      );
    }

    // Group offers by valid status
    final pendingOffers = _offers.where((o) => o.status == WorkerOffer.pending).toList();
    final acceptedOffers = _offers.where((o) => o.status == WorkerOffer.accepted).toList();
    final otherOffers = _offers.where((o) => [WorkerOffer.declined, WorkerOffer.expired, WorkerOffer.withdrawn].contains(o.status)).toList();

    if (pendingOffers.isEmpty && acceptedOffers.isEmpty && otherOffers.isEmpty) {
      return const Center(
        child: Text('No job offers'),
      );
    }

    return RefreshIndicator(
      onRefresh: _refresh,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (acceptedOffers.isNotEmpty) ...[
            const Text('Accepted Offers', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            ...acceptedOffers.map((o) => _buildOfferCard(o, isAccepted: true)),
          ],
          if (pendingOffers.isNotEmpty) ...[
            const SizedBox(height: 16),
            const Text('Pending Offers', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            ...pendingOffers.map((o) => _buildOfferCard(o, isAccepted: false)),
          ],
          if (otherOffers.isNotEmpty) ...[
            const SizedBox(height: 16),
            const Text('Completed/Expired', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            ...otherOffers.take(3).map((o) => _buildOfferCard(o, isAccepted: false)),
          ],
        ],
      ),
    );
  }

  Widget _buildOfferCard(WorkerOffer offer, {required bool isAccepted}) {
    final inProgress = _actionInProgress == offer.id;

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: ListTile(
        title: Text('Booking #${offer.bookingId}', style: const TextStyle(fontWeight: FontWeight.bold)),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (offer.serviceTitle?.isNotEmpty == true)
              Text(offer.serviceTitle!, style: const TextStyle(fontWeight: FontWeight.w700)),
            if (offer.variantTitle?.isNotEmpty == true || offer.quantity > 1)
              Text(
                [if (offer.variantTitle?.isNotEmpty == true) offer.variantTitle!, 'Qty ${offer.quantity}'].join(' • '),
                style: const TextStyle(fontSize: 12),
              ),
            if (offer.scheduledAt != null)
              Text('Requested: ${_formatDateTime(offer.scheduledAt!)}'),
            if (offer.serviceAddress?.isNotEmpty == true)
              Text('Area: ${offer.serviceAddress}', maxLines: 2, overflow: TextOverflow.ellipsis),
            Text('Expected duration: ${offer.expectedDurationMinutes} minutes',
                style: const TextStyle(fontSize: 12)),
            if (offer.bookingNotes?.trim().isNotEmpty == true)
              Text('Customer instructions: ${offer.bookingNotes}',
                  style: const TextStyle(fontSize: 12)),
            if (offer.customerTotal > 0)
              Text('Customer total: ₹${offer.customerTotal.toStringAsFixed(2)}'),
            if (offer.advanceReceived > 0)
              Text('Advance received: ₹${offer.advanceReceived.toStringAsFixed(2)}',
                  style: const TextStyle(color: Colors.green, fontWeight: FontWeight.w600)),
            if (offer.remainingBalance > 0)
              Text('Customer balance: ₹${offer.remainingBalance.toStringAsFixed(2)}'),
            for (final entry in offer.customerAnswers.entries)
              Text(
                workerCustomerAnswerLabel(entry.key, entry.value),
                style: const TextStyle(fontSize: 12),
              ),
            for (final answer in offer.formResponses)
              Text(
                '${answer['label'] ?? answer['key']}: ${answer['value']}',
                style: const TextStyle(fontSize: 12),
              ),
            if (offer.addons.isNotEmpty)
              Text(
                'Add-ons: ${offer.addons.map((addon) => addon['title']).join(', ')}',
                style: const TextStyle(fontSize: 12),
              ),
            Text('Offered: ${_formatDateTime(offer.offeredAt)}'),
            if (offer.expiresAt != null && offer.status == WorkerOffer.pending)
              _buildExpiryCountdown(offer),
            if (offer.status == WorkerOffer.accepted)
              Text('Status: Accepted', style: TextStyle(color: Colors.green[700])),
          ],
        ),
        trailing: _buildActionButtons(offer, inProgress, isAccepted),
      ),
    );
  }

  Widget _buildExpiryCountdown(WorkerOffer offer) {
    final countdown = _timeRemaining[offer.id] ?? offer.expiresAt!.difference(DateTime.now());
    final minutes = countdown.inMinutes;
    final seconds = countdown.inSeconds % 60;

    Color timeColor = Colors.green;
    if (countdown.inMinutes < 2) {
      timeColor = Colors.orange;
    }
    if (countdown.inSeconds < 30) {
      timeColor = Colors.red;
    }

    return Text(
      'Expires in: ${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')}',
      style: TextStyle(color: timeColor, fontSize: 12, fontWeight: FontWeight.w500),
    );
  }

  Widget _buildActionButtons(WorkerOffer offer, bool inProgress, bool isAccepted) {
    final status = offer.status;

    // Accepted offers show status only
    if (status == WorkerOffer.accepted) {
      return Chip(
        label: const Text('Accepted', style: TextStyle(fontSize: 12)),
        backgroundColor: Colors.green.shade100,
      );
    }

    // Declined offers show status
    if (status == WorkerOffer.declined) {
      return Chip(
        label: const Text('Declined'),
        backgroundColor: Colors.red.shade100,
      );
    }

    // Expired offers show status
    if (status == WorkerOffer.expired) {
      return Chip(
        label: const Text('Expired'),
        backgroundColor: Colors.grey.shade200,
      );
    }

    // Withdrawn offers show status
    if (status == WorkerOffer.withdrawn) {
      return Chip(
        label: const Text('Withdrawn'),
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
              child: const Text('Decline'),
            ),
          const SizedBox(width: 8),
          if (offer.canAccept)
            FilledButton(
              onPressed: () => _acceptOffer(offer.id),
              child: const Text('Accept'),
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