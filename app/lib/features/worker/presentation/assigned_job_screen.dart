import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:geolocator/geolocator.dart';
import 'package:intl/intl.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/worker/data/worker_api.dart';
import 'package:airway/core/localization/airway_text.dart';
import 'package:airway/features/worker/data/worker_models.dart';
import 'package:airway/features/booking/data/booking_models.dart';
import 'package:airway/features/booking/data/booking_api.dart';
import 'package:airway/features/ratings/data/rating_api.dart';

class AssignedJobScreen extends StatefulWidget {
  const AssignedJobScreen({super.key, this.assignmentId});

  final int? assignmentId;

  @override
  State<AssignedJobScreen> createState() => _AssignedJobScreenState();
}

class _AssignedJobScreenState extends State<AssignedJobScreen> with WidgetsBindingObserver {
  WorkerAssignmentDetail? _jobDetail;
  List<Map<String, dynamic>> _jobDisputes = [];
  bool _loading = true;
  String? _error;
  bool _isActionInProgress = false;
  bool _hasRatedCustomer = false;
  Timer? _locationTimer;
  Timer? _contactRefreshTimer;
  int? _sharingAssignmentId;
  bool _locationRequestInProgress = false;
  bool _locationPermissionBlocked = false;
  bool _locationSharingEnabled = false;
  bool _locationConsentRequestInProgress = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _loadAssignedJob();
  }

  @override
  void dispose() {
    _locationTimer?.cancel();
    _contactRefreshTimer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && _jobDetail != null) {
      _locationPermissionBlocked = false;
      _configureLocationSharing(_jobDetail!);
      _refreshContactAccess();
    } else if (state != AppLifecycleState.resumed) {
      _locationTimer?.cancel();
      _locationTimer = null;
    }
  }

  bool _canShareLocation(WorkerAssignmentDetail job) =>
      job.status == BookingStatus.assigned ||
      job.status == BookingStatus.inProgress;

  void _configureLocationSharing(WorkerAssignmentDetail job) {
    if (!_canShareLocation(job) || !_locationSharingEnabled) {
      _locationTimer?.cancel();
      _locationTimer = null;
      _sharingAssignmentId = null;
      return;
    }
    final visibilityStartsAt = job.scheduledAt.subtract(const Duration(minutes: 30));
    final now = DateTime.now();
    if (now.isBefore(visibilityStartsAt)) {
      _locationTimer?.cancel();
      _sharingAssignmentId = null;
      _locationTimer = Timer(
        visibilityStartsAt.difference(now),
        () => _configureLocationSharing(job),
      );
      return;
    }
    if (WidgetsBinding.instance.lifecycleState != AppLifecycleState.resumed) return;
    if (_sharingAssignmentId != job.assignmentId) {
      _locationTimer?.cancel();
      _sharingAssignmentId = job.assignmentId;
      _publishCurrentLocation(job.assignmentId);
      _locationTimer = Timer.periodic(
        const Duration(seconds: 30),
        (_) => _publishCurrentLocation(job.assignmentId),
      );
    }
  }

  Future<void> _setLocationSharing(bool enabled) async {
    final job = _jobDetail;
    if (job == null || _locationConsentRequestInProgress) return;
    setState(() => _locationConsentRequestInProgress = true);
    try {
      await WorkerApi.setJobLocationSharing(
        job.assignmentId,
        enabled: enabled,
      );
      if (!mounted) return;
      setState(() {
        _locationSharingEnabled = enabled;
        _locationConsentRequestInProgress = false;
        if (enabled) _locationPermissionBlocked = false;
      });
      if (!enabled) {
        _locationTimer?.cancel();
        _locationTimer = null;
        _sharingAssignmentId = null;
      } else {
        _configureLocationSharing(job);
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _locationConsentRequestInProgress = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr(
          'Could not update location-sharing permission: $e',
          'लोकेशन शेयरिंग अनुमति अपडेट नहीं हो सकी: $e',
        ))),
      );
    }
  }

  Future<void> _publishCurrentLocation(int assignmentId) async {
    if (!mounted || _locationRequestInProgress || _locationPermissionBlocked ||
        WidgetsBinding.instance.lifecycleState != AppLifecycleState.resumed) return;
    _locationRequestInProgress = true;
    try {
      if (!await Geolocator.isLocationServiceEnabled()) return;
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        _locationPermissionBlocked = true;
        return;
      }
      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 12),
        ),
      );
      if (!mounted ||
          _sharingAssignmentId != assignmentId ||
          WidgetsBinding.instance.lifecycleState != AppLifecycleState.resumed) {
        return;
      }
      await WorkerApi.updateJobLocation(
        assignmentId,
        latitude: position.latitude,
        longitude: position.longitude,
        accuracyMeters: position.accuracy,
      );
    } catch (_) {
      // Location is optional; the job lifecycle remains usable without GPS/network.
    } finally {
      _locationRequestInProgress = false;
    }
  }

  Future<void> _loadAssignedJob() async {
    if (mounted) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final jobs = await WorkerApi.getAssignedJobs();

      if (jobs.isEmpty) {
        _locationTimer?.cancel();
        _locationTimer = null;
        _sharingAssignmentId = null;
        if (mounted) {
          setState(() {
            _loading = false;
          });
        }
        return;
      }

      // Open the selected assignment when launched from a job card;
      // otherwise keep the existing first-job fallback.
      final matchingJobs = widget.assignmentId == null
          ? jobs
          : jobs.where((job) => job['id'] == widget.assignmentId).toList();
      if (matchingJobs.isEmpty) {
        _locationTimer?.cancel();
        _locationTimer = null;
        _sharingAssignmentId = null;
        if (mounted) {
          setState(() {
            _error = AirwayText.tr('This job is no longer assigned to your account.', 'यह जॉब अब आपके खाते को असाइन नहीं है।');
            _loading = false;
          });
        }
        return;
      }

      // Get full job details for this exact assignment.
      final selectedJob = matchingJobs.first;
      final detail = await WorkerApi.getJobDetail(selectedJob['id'] as int);
      final parsedDetail = WorkerAssignmentDetail.fromMap(detail);
      var hasRatedCustomer = false;
      try {
        final ratings = await RatingApi.fetchUserRatings();
        hasRatedCustomer = ratings.any((rating) =>
            rating.bookingId == parsedDetail.bookingId &&
            rating.ratingType == 'worker');
      } catch (_) {
        // Keep the job screen usable if rating history is temporarily unavailable.
      }
      if (mounted) {
        _jobDetail = parsedDetail;
        _scheduleContactUnlock(parsedDetail);
        setState(() {
          _hasRatedCustomer = hasRatedCustomer;
          _locationSharingEnabled = parsedDetail.assignment.locationSharingEnabled;
          _loading = false;
        });
        _configureLocationSharing(parsedDetail);
        _loadJobDisputes(parsedDetail.bookingId);
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = AirwayText.tr('Could not load assigned job: $e', 'असाइन की गई जॉब लोड नहीं हो सकी: $e');
          _loading = false;
        });
      }
    }
  }

  void _scheduleContactUnlock(WorkerAssignmentDetail job) {
    _contactRefreshTimer?.cancel();
    if (job.status != BookingStatus.assigned &&
        job.status != BookingStatus.inProgress) return;

    // Keep checking after unlock too: a reschedule or terminal status must
    // revoke a phone number that was previously visible in this screen.
    if (job.customerContactAvailable) {
      _contactRefreshTimer = Timer(const Duration(minutes: 1), _refreshContactAccess);
      return;
    }
    if (job.customerContactAvailableAt == null) return;

    final delay = job.customerContactAvailableAt!.difference(DateTime.now());
    final refreshAfter = delay.isNegative
        ? const Duration(minutes: 1)
        : (delay > const Duration(minutes: 5)
            ? const Duration(minutes: 5)
            : delay + const Duration(seconds: 3));
    _contactRefreshTimer = Timer(refreshAfter, _refreshContactAccess);
  }

  Future<void> _refreshContactAccess() async {
    final current = _jobDetail;
    if (!mounted || current == null ||
        WidgetsBinding.instance.lifecycleState != AppLifecycleState.resumed) return;
    try {
      final data = await WorkerApi.getJobDetail(current.assignmentId);
      if (!mounted) return;
      final updated = WorkerAssignmentDetail.fromMap(data);
      setState(() => _jobDetail = updated);
      _scheduleContactUnlock(updated);
    } catch (_) {
      // Retry on a short interval without interrupting the active job.
      if (mounted) _scheduleContactUnlock(current);
    }
  }

  Future<String?> _requestArrivalOtp() async {
    final controller = TextEditingController();
    final code = await showDialog<String>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) => AlertDialog(
        title: Text(AirwayText.tr('Customer arrival code', 'ग्राहक का आगमन कोड')),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(AirwayText.tr(
              'Ask the customer for the 6-digit code sent to their AIRway notifications. Work cannot start until the customer shares it.',
              'ग्राहक से AIRway नोटिफ़िकेशन में भेजा गया 6 अंकों का कोड लें। ग्राहक के कोड के बिना काम शुरू नहीं होगा।',
            )),
            const SizedBox(height: 14),
            TextField(
              controller: controller,
              autofocus: true,
              keyboardType: TextInputType.number,
              maxLength: 6,
              decoration: InputDecoration(
                labelText: AirwayText.tr('6-digit arrival code', '6 अंकों का आगमन कोड'),
                border: const OutlineInputBorder(),
                counterText: '',
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: Text(AirwayText.tr('Not now', 'अभी नहीं')),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, controller.text.trim()),
            child: Text(AirwayText.tr('Verify and start', 'वेरिफ़ाई करके शुरू करें')),
          ),
        ],
      ),
    );
    controller.dispose();
    return code;
  }

  Future<void> _startJob() async {
    if (!mounted || _jobDetail == null) return;

    setState(() {
      _isActionInProgress = true;
    });

    try {
      var result = await WorkerApi.startJob(_jobDetail!.assignmentId);
      if (result['arrival_otp_required'] == true) {
        final arrivalOtp = await _requestArrivalOtp();
        if (arrivalOtp == null || arrivalOtp.isEmpty) return;
        result = await WorkerApi.startJob(
          _jobDetail!.assignmentId,
          arrivalOtp: arrivalOtp,
        );
        if (result['arrival_otp_required'] == true) {
          throw Exception(result['detail'] ?? 'Customer arrival code is required.');
        }
      }
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(AirwayText.tr('Arrival verified. Appointment started.', 'आगमन वेरिफ़ाई हो गया। अपॉइंटमेंट शुरू हो गया।')) ),
        );
        await _loadAssignedJob();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(AirwayText.tr('Failed to start job: $e', 'काम शुरू नहीं हो सका: $e'))),
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _isActionInProgress = false;
        });
      }
    }
  }


  Future<void> _proposeExtraWork() async {
    final job = _jobDetail;
    if (job == null || job.status != BookingStatus.inProgress || _isActionInProgress) return;
    final reasonController = TextEditingController();
    final descriptionController = TextEditingController();
    final priceController = TextEditingController();
    final quantityController = TextEditingController(text: '1');
    final durationController = TextEditingController(text: '0');
    final proposal = await showDialog<Map<String, String>>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Request additional work'),
        content: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Text('Explain why the additional work is needed and enter its price. The customer must approve it before any extra charge is made.'),
            const SizedBox(height: 12),
            TextField(controller: reasonController, maxLength: 500, maxLines: 2,
              decoration: const InputDecoration(labelText: 'Reason', border: OutlineInputBorder())),
            const SizedBox(height: 8),
            TextField(controller: descriptionController, maxLength: 250,
              decoration: const InputDecoration(labelText: 'Additional work item', border: OutlineInputBorder())),
            const SizedBox(height: 8),
            Row(children: [
              Expanded(child: TextField(controller: quantityController, keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'Quantity', border: OutlineInputBorder()))),
              const SizedBox(width: 8),
              Expanded(child: TextField(controller: priceController, keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'Unit price (₹)', border: OutlineInputBorder()))),
            ]),
            const SizedBox(height: 8),
            TextField(controller: durationController, keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Extra time (minutes)', border: OutlineInputBorder())),
          ]),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Cancel')),
          FilledButton(onPressed: () {
            final reason = reasonController.text.trim();
            final description = descriptionController.text.trim();
            final quantity = int.tryParse(quantityController.text.trim());
            final price = double.tryParse(priceController.text.trim());
            final duration = int.tryParse(durationController.text.trim());
            if (reason.isEmpty || description.isEmpty || quantity == null || quantity < 1 ||
                price == null || !price.isFinite || price <= 0 ||
                duration == null || duration < 0 || duration > 600) {
              ScaffoldMessenger.of(dialogContext).showSnackBar(
                const SnackBar(content: Text('Enter a reason, item, valid quantity, positive price and extra time between 0 and 600 minutes.')),
              );
              return;
            }
            Navigator.pop(dialogContext, {
              'reason': reason,
              'description': description,
              'quantity': quantity.toString(),
              'unit_price': price.toStringAsFixed(2),
              'duration': duration.toString(),
            });
          }, child: const Text('Send for approval')),
        ],
      ),
    );
    reasonController.dispose();
    descriptionController.dispose();
    priceController.dispose();
    quantityController.dispose();
    durationController.dispose();
    if (proposal == null || !mounted) return;
    setState(() => _isActionInProgress = true);
    try {
      final extraWork = await WorkerApi.proposeExtraWork(
        job.bookingId,
        reason: proposal['reason']!,
        description: proposal['description']!,
        quantity: int.parse(proposal['quantity']!),
        unitPrice: proposal['unit_price']!,
        additionalDurationMinutes: int.parse(proposal['duration']!),
      );
      await _loadAssignedJob();
      if (!mounted) return;
      final payout = extraWork['worker_payout_amount']?.toString();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            payout == null
                ? 'Extra-work request sent. Wait for customer approval.'
                : 'Request sent. Your additional payout after approval and payment: ₹$payout.',
          ),
          duration: const Duration(seconds: 5),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not send extra-work request: ' + e.toString())));
    } finally {
      if (mounted) setState(() => _isActionInProgress = false);
    }
  }

  Future<void> _raiseJobDispute(WorkerAssignmentDetail job) async {
    final descriptionController = TextEditingController();
    var category = 'service_quality';
    var outcome = 'investigation';
    File? evidencePhoto;
    final payload = await showDialog<Map<String, String>>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (dialogContext, setDialogState) => AlertDialog(
          title: Text(AirwayText.tr('Report a job concern', 'जॉब से जुड़ी समस्या रिपोर्ट करें')),
          content: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              DropdownButtonFormField<String>(
                value: category,
                decoration: InputDecoration(labelText: AirwayText.tr('Concern type', 'समस्या का प्रकार')),
                items: const [
                  DropdownMenuItem(value: 'service_quality', child: Text('Service quality')),
                  DropdownMenuItem(value: 'damage', child: Text('Property damage')),
                  DropdownMenuItem(value: 'payment', child: Text('Payment')),
                  DropdownMenuItem(value: 'customer_conduct', child: Text('Customer conduct')),
                  DropdownMenuItem(value: 'safety', child: Text('Safety concern')),
                  DropdownMenuItem(value: 'other', child: Text('Other')),
                ],
                onChanged: (value) => setDialogState(() => category = value ?? category),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                value: outcome,
                decoration: InputDecoration(labelText: AirwayText.tr('Support needed', 'किस सहायता की ज़रूरत है?')),
                items: const [
                  DropdownMenuItem(value: 'investigation', child: Text('Investigation')),
                  DropdownMenuItem(value: 'rework', child: Text('Service recovery')),
                  DropdownMenuItem(value: 'refund_review', child: Text('Payment review')),
                  DropdownMenuItem(value: 'other', child: Text('Other')),
                ],
                onChanged: (value) => setDialogState(() => outcome = value ?? outcome),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: descriptionController,
                maxLines: 4,
                maxLength: 5000,
                decoration: InputDecoration(
                  labelText: AirwayText.tr('Describe the concern', 'समस्या का विवरण दें'),
                  border: const OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 8),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: () async {
                    final picked = await ImagePicker().pickImage(
                      source: ImageSource.gallery,
                      imageQuality: 85,
                    );
                    if (picked != null) {
                      setDialogState(() => evidencePhoto = File(picked.path));
                    }
                  },
                  icon: const Icon(Icons.add_photo_alternate_outlined),
                  label: Text(evidencePhoto == null
                      ? AirwayText.tr('Attach evidence photo (optional)', 'सबूत की फ़ोटो जोड़ें (वैकल्पिक)')
                      : AirwayText.tr('Evidence photo selected', 'सबूत की फ़ोटो चुनी गई')),
                ),
              ),
            ]),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dialogContext), child: Text(AirwayText.tr('Cancel', 'रद्द करें'))),
            FilledButton(
              onPressed: () {
                if (descriptionController.text.trim().isEmpty) return;
                Navigator.pop(dialogContext, {
                  'category': category,
                  'requested_outcome': outcome,
                  'description': descriptionController.text.trim(),
                });
              },
              child: Text(AirwayText.tr('Submit', 'जमा करें')),
            ),
          ],
        ),
      ),
    );
    descriptionController.dispose();
    if (payload == null || !mounted) return;
    try {
      final dispute = await BookingApi.createDispute(
        bookingId: job.bookingId,
        category: payload['category']!,
        description: payload['description']!,
        requestedOutcome: payload['requested_outcome']!,
      );
      var message = AirwayText.tr(
        'Your concern was sent to AIRway support.',
        'आपकी समस्या AIRway सपोर्ट को भेज दी गई है।',
      );
      if (evidencePhoto != null) {
        try {
          await BookingApi.uploadDisputeEvidence(
            disputeId: int.parse(dispute['id'].toString()),
            photo: evidencePhoto!,
          );
        } catch (uploadError) {
          message = AirwayText.tr(
            'Report submitted, but evidence upload failed: $uploadError',
            'रिपोर्ट भेज दी गई, लेकिन सबूत अपलोड नहीं हुआ: $uploadError',
          );
        }
      }
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
      await _loadAssignedJob();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Could not submit concern: $e', 'समस्या भेजी नहीं जा सकी: $e'))),
      );
    }
  }

  Future<void> _loadJobDisputes(int bookingId) async {
    try {
      final all = await BookingApi.getDisputes();
      if (!mounted) return;
      setState(() {
        _jobDisputes = all.where((item) =>
            int.tryParse(item['booking_id']?.toString() ?? '') == bookingId).toList();
      });
    } catch (_) {
      // Keep the assigned-job flow available if support history is unavailable.
    }
  }

  Widget _buildDisputeHistoryCard() {
    if (_jobDisputes.isEmpty) return const SizedBox.shrink();
    return Card(
      color: Colors.white,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: const BorderSide(color: Color(0xFFE8E2F5)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            const Icon(Icons.history_rounded, color: Color(0xFF6C4AE3)),
            const SizedBox(width: 9),
            Expanded(child: Text(
              AirwayText.tr('Support case history', 'सपोर्ट केस का इतिहास'),
              style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 16),
            )),
          ]),
          const SizedBox(height: 8),
          for (final item in _jobDisputes) ...[
            Row(children: [
              Expanded(child: Text(
                (item['category']?.toString() ?? 'other').replaceAll('_', ' '),
                style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
              )),
              Text(
                (item['status']?.toString() ?? 'open').replaceAll('_', ' ').toUpperCase(),
                style: const TextStyle(fontWeight: FontWeight.w800, color: Color(0xFF6C4AE3), fontSize: 10),
              ),
            ]),
            if ((item['resolution_note']?.toString() ?? '').isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(item['resolution_note'].toString(),
                  style: const TextStyle(color: AirwayColors.textSecondary, fontSize: 12)),
            ],
            for (final event in (item['status_history'] as List? ?? const []).whereType<Map>())
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  '${(event['to_status']?.toString() ?? '').replaceAll('_', ' ').toUpperCase()}${(event['note']?.toString() ?? '').isNotEmpty ? ' — ${event['note']}' : ''}',
                  style: const TextStyle(color: AirwayColors.textSecondary, fontSize: 11),
                ),
              ),
            finalEvidenceCount(item),
            if (_jobDisputes.last != item) const Divider(height: 16),
          ],
        ]),
      ),
    );
  }

  Widget finalEvidenceCount(Map<String, dynamic> item) {
    final files = item['evidence_files'] as List? ?? const [];
    if (files.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Text(
        AirwayText.tr('${files.length} evidence photo(s) attached', '${files.length} सबूत की फ़ोटो संलग्न'),
        style: const TextStyle(color: AirwayColors.textSecondary, fontSize: 11),
      ),
    );
  }


  Widget _buildReworkCaseCard(WorkerAssignmentDetail job) {
    final recovery = job.reworkCase;
    if (recovery == null) return const SizedBox.shrink();
    final evidence = (recovery['evidence_files'] as List? ?? [])
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
    return Card(
      color: const Color(0xFFFFFBF2),
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: Color(0xFFF0DFC1)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            const Icon(Icons.replay_circle_filled_rounded, color: Color(0xFF9A6418)),
            const SizedBox(width: 8),
            Expanded(child: Text(
              AirwayText.tr('Service recovery instructions', 'सेवा सुधार के निर्देश'),
              style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 15),
            )),
            Text(
              (recovery['category']?.toString() ?? 'other').replaceAll('_', ' '),
              style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w800),
            ),
          ]),
          const SizedBox(height: 9),
          Text(
            recovery['description']?.toString() ?? '',
            style: const TextStyle(fontSize: 13, height: 1.4),
          ),
          if ((recovery['resolution_note']?.toString() ?? '').isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              'AIRway decision: ${recovery['resolution_note']}',
              style: const TextStyle(fontSize: 12, color: AirwayColors.textSecondary),
            ),
          ],
          for (final event in (recovery['status_history'] as List? ?? const []).whereType<Map>())
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                '${(event['to_status']?.toString() ?? '').replaceAll('_', ' ').toUpperCase()}${(event['note']?.toString() ?? '').isNotEmpty ? ' — ${event['note']}' : ''}',
                style: const TextStyle(fontSize: 11, color: AirwayColors.textSecondary),
              ),
            ),
          if (evidence.isNotEmpty) ...[
            const SizedBox(height: 12),
            Text(
              AirwayText.tr('Customer evidence', 'ग्राहक के सबूत'),
              style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 12),
            ),
            const SizedBox(height: 8),
            SizedBox(
              height: 104,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: evidence.length,
                separatorBuilder: (_, __) => const SizedBox(width: 8),
                itemBuilder: (context, index) {
                  final photo = evidence[index];
                  final url = photo['photo_url']?.toString() ?? '';
                  return ClipRRect(
                    borderRadius: BorderRadius.circular(10),
                    child: FutureBuilder<Map<String, String>>(
                      future: WorkerApi.getAuthHeaders(),
                      builder: (context, snapshot) {
                        if (snapshot.hasError) {
                          return Container(
                            width: 104,
                            color: Colors.black12,
                            alignment: Alignment.center,
                            child: const Icon(Icons.broken_image_outlined),
                          );
                        }
                        if (!snapshot.hasData) {
                          return Container(
                            width: 104,
                            color: Colors.black12,
                            alignment: Alignment.center,
                            child: const CircularProgressIndicator(strokeWidth: 2),
                          );
                        }
                        return Image.network(
                          url,
                          headers: snapshot.data,
                          width: 104,
                          height: 104,
                          fit: BoxFit.cover,
                          errorBuilder: (_, __, ___) => Container(
                            width: 104,
                            color: Colors.black12,
                            alignment: Alignment.center,
                            child: const Icon(Icons.broken_image_outlined),
                          ),
                        );
                      },
                    ),
                  );
                },
              ),
            ),
          ],
        ]),
      ),
    );
  }

  Widget _buildDisputeCard(WorkerAssignmentDetail job) {
    final canReport = job.status == BookingStatus.inProgress ||
        job.status == BookingStatus.completed;
    if (!canReport) return const SizedBox.shrink();
    return Card(
      color: Colors.white,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: const BorderSide(color: Color(0xFFE8E2F5)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            const Icon(Icons.support_agent_rounded, color: Color(0xFF6C4AE3)),
            const SizedBox(width: 9),
            Expanded(child: Text(
              AirwayText.tr('AIRway support', 'AIRway सहायता'),
              style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 16),
            )),
          ]),
          const SizedBox(height: 7),
          Text(AirwayText.tr(
            'If there is a safety, conduct, payment or service concern, report it to AIRway support for review.',
            'सुरक्षा, व्यवहार, भुगतान या सेवा से जुड़ी समस्या होने पर AIRway सपोर्ट को रिपोर्ट करें।',
          ), style: const TextStyle(color: AirwayColors.textSecondary, fontSize: 13)),
          const SizedBox(height: 10),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: _isActionInProgress ? null : () => _raiseJobDispute(job),
              icon: const Icon(Icons.flag_outlined),
              label: Text(AirwayText.tr('Report a concern', 'समस्या रिपोर्ट करें')),
            ),
          ),
        ]),
      ),
    );
  }

  Widget _buildExtraWorkCard(WorkerAssignmentDetail job) {
    final canPropose = job.status == BookingStatus.inProgress;
    if (!canPropose && job.extraWorkRequests.isEmpty) return const SizedBox.shrink();
    return Card(
      color: Colors.white,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: const BorderSide(color: Color(0xFFE8E2F5)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Container(
              width: 34,
              height: 34,
              decoration: BoxDecoration(
                color: const Color(0xFFF1EDFF),
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Icon(Icons.add_task_rounded, color: Color(0xFF6C4AE3), size: 19),
            ),
            const SizedBox(width: 9),
            const Expanded(child: Text(
              'Additional work',
              style: TextStyle(fontWeight: FontWeight.w900, fontSize: 16),
            )),
          ]),
          if (canPropose) ...[
            const SizedBox(height: 7),
            const Text(
              'If the customer needs work beyond the booked service, send a priced request. Do not start or charge for it until the customer approves.',
              style: TextStyle(color: AirwayColors.textSecondary, fontSize: 13),
            ),
          ],
          if (job.extraWorkRequests.isNotEmpty) ...[
            const SizedBox(height: 14),
            const Divider(),
            const Text('Request history', style: TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            ...job.extraWorkRequests.map((request) {
              final status = request['status']?.toString() ?? 'pending_customer';
              final label = switch (status) {
                'approved' => 'Approved',
                'rejected' => 'Declined',
                'expired' => 'Expired',
                'cancelled' => 'Cancelled',
                _ => 'Awaiting customer',
              };
              final labelColor = switch (status) {
                'approved' => AirwayColors.success,
                'rejected' || 'cancelled' => AirwayColors.error,
                'expired' => AirwayColors.warning,
                _ => const Color(0xFF6C4AE3),
              };
              final labelBackground = switch (status) {
                'approved' => AirwayColors.successSoft,
                'rejected' || 'cancelled' => AirwayColors.errorSoft,
                'expired' => AirwayColors.warningSoft,
                _ => const Color(0xFFF1EDFF),
              };
              final paymentStatus = request['payment_status']?.toString() ?? 'not_due';
              final paymentLabel = paymentStatus == 'paid'
                  ? 'Paid'
                  : paymentStatus == 'pending'
                      ? 'Payment pending'
                      : '';
              final items = (request['line_items'] as List? ?? [])
                  .whereType<Map>()
                  .map((item) => item['description']?.toString() ?? '')
                  .where((value) => value.isNotEmpty)
                  .join(', ');
              return Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: const Color(0xFFFBFAFF),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: const Color(0xFFE8E2F5)),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Align(
                              alignment: Alignment.centerLeft,
                              child: Container(
                                padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
                                decoration: BoxDecoration(
                                  color: labelBackground,
                                  borderRadius: BorderRadius.circular(20),
                                ),
                                child: Text(
                                  label,
                                  style: TextStyle(
                                    fontWeight: FontWeight.w800,
                                    color: labelColor,
                                    fontSize: 11,
                                  ),
                                ),
                              ),
                            ),
                          ),
                          Text('₹${request['total_amount'] ?? '0.00'}', style: const TextStyle(fontWeight: FontWeight.w900, color: Color(0xFF6C4AE3))),
                        ],
                      ),
                      if ((request['reason']?.toString() ?? '').isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Text(request['reason'].toString()),
                        ),
                      if (items.isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Text(items, style: TextStyle(fontSize: 12, color: AirwayColors.textSecondary)),
                        ),
                      if ((request['additional_duration_minutes'] as num? ?? 0) > 0)
                        Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Text(
                            'Additional time: ${request['additional_duration_minutes']} minutes',
                            style: const TextStyle(fontSize: 12, color: AirwayColors.textSecondary),
                          ),
                        ),
                      if (paymentLabel.isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Text(paymentLabel, style: TextStyle(fontSize: 12, color: AirwayColors.textSecondary)),
                        ),
                      if ((request['customer_response_note']?.toString() ?? '').isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Text('Customer note: ${request['customer_response_note']}'),
                        ),
                    ],
                  ),
                ),
              );
            }),
          ],
          if (canPropose) ...[
            const SizedBox(height: 10),
            SizedBox(width: double.infinity, child: FilledButton.icon(
              onPressed: _isActionInProgress ? null : _proposeExtraWork,
              icon: const Icon(Icons.add_task_rounded),
              label: const Text('Request customer approval'),
            )),
          ],
        ]),
      ),
    );
  }

  Future<void> _recordCashReceived(WorkerAssignmentDetail job) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(AirwayText.tr('Confirm cash received', 'नकद भुगतान की पुष्टि करें')),
        content: Text(AirwayText.tr(
          'Confirm only if the customer has handed you the remaining balance in cash. The customer completion OTP has already been verified.',
          'केवल तभी पुष्टि करें जब ग्राहक ने बाकी राशि नकद दे दी हो। ग्राहक का पूरा करने वाला OTP पहले ही वेरिफ़ाई हो चुका है।',
        )),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: Text(AirwayText.tr('Cancel', 'रद्द करें')),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: Text(AirwayText.tr('Cash received', 'नकद मिल गया')),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _isActionInProgress = true);
    try {
      final result = await WorkerApi.recordCashReceived(job.assignmentId);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(result['detail']?.toString() ??
              AirwayText.tr('Cash balance recorded.', 'नकद बकाया दर्ज हो गया।')),
        ),
      );
      await _loadAssignedJob();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Could not record cash: $e', 'नकद भुगतान दर्ज नहीं हो सका: $e'))),
      );
    } finally {
      if (mounted) setState(() => _isActionInProgress = false);
    }
  }

  Future<void> _completeJob() async {
    if (!mounted || _jobDetail == null) return;
    setState(() => _isActionInProgress = true);
    try {
      final issued = await WorkerApi.completeJob(_jobDetail!.assignmentId);
      if (!mounted) return;
      setState(() => _isActionInProgress = false);
      if (issued['otp_required'] != true) {
        throw Exception(issued['detail'] ?? 'Could not request completion code.');
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(AirwayText.tr('Ask the customer to share the 6-digit completion code shown in their AIRway notifications.', 'ग्राहक से AIRway नोटिफ़िकेशन में दिखा 6 अंकों का पूरा करने वाला कोड साझा करने को कहें।')),
          duration: Duration(seconds: 5),
        ),
      );
      final controller = TextEditingController();
      final code = await showDialog<String>(
        context: context,
        barrierDismissible: false,
        builder: (dialogContext) => AlertDialog(
          title: Text(AirwayText.tr('Verify service completion', 'सेवा पूरी होने की पुष्टि करें')),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(AirwayText.tr('Enter the 6-digit code shared by the customer after the service is finished.', 'सेवा पूरी होने के बाद ग्राहक द्वारा साझा किया गया 6 अंकों का कोड दर्ज करें।')),
              const SizedBox(height: 14),
              TextField(
                controller: controller,
                autofocus: true,
                keyboardType: TextInputType.number,
                maxLength: 6,
                decoration: InputDecoration(
                  labelText: AirwayText.tr('Customer completion code', 'ग्राहक का सेवा-समाप्ति कोड'),
                  border: OutlineInputBorder(),
                  counterText: '',
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: Text(AirwayText.tr('Cancel', 'रद्द करें')),
            ),
            FilledButton(
              onPressed: () {
                final value = controller.text.trim();
                if (RegExp(r'^[0-9]{6}$').hasMatch(value)) {
                  Navigator.pop(dialogContext, value);
                }
              },
              child: Text(AirwayText.tr('Verify & complete', 'पुष्टि करें और पूरा करें')),
            ),
          ],
        ),
      );
      controller.dispose();
      if (code == null || !mounted) {
        await _loadAssignedJob();
        return;
      }
      setState(() => _isActionInProgress = true);
      final result = await WorkerApi.completeJob(
        _jobDetail!.assignmentId,
        otp: code,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(result['detail']?.toString() ?? AirwayText.tr('Completion verified.', 'सेवा पूरी होने की पुष्टि हो गई।'))),
        );
        await _loadAssignedJob();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(AirwayText.tr('Completion verification failed: $e', 'सेवा पूरी होने की पुष्टि विफल: $e'))),
        );
      }
    } finally {
      if (mounted) setState(() => _isActionInProgress = false);
    }
  }
  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return Scaffold(
        appBar: AppBar(title: Text(AirwayText.tr('Assigned Job', 'असाइन की गई जॉब'))),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    if (_error != null) {
      return Scaffold(
        appBar: AppBar(title: Text(AirwayText.tr('Assigned Job', 'असाइन की गई जॉब'))),
        body: _errorWidget(_error!),
      );
    }

    if (_jobDetail == null) {
      return Scaffold(
        appBar: AppBar(title: Text(AirwayText.tr('Assigned Job', 'असाइन की गई जॉब'))),
        body: Center(child: Text(AirwayText.tr('No assigned job', 'कोई जॉब असाइन नहीं है'))),
      );
    }

    final job = _jobDetail!;
    return Scaffold(
      appBar: AppBar(
        title: Text(AirwayText.tr('Assigned Job', 'असाइन की गई जॉब')),
      ),
      body: RefreshIndicator(
        onRefresh: _loadAssignedJob,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _buildServiceInfo(job),
            const SizedBox(height: 16),
            _buildScheduleInfo(job),
            const SizedBox(height: 16),
            _buildCustomerInfo(job),
            const SizedBox(height: 16),
            _buildAssignmentInfo(job),
            const SizedBox(height: 16),
            _buildPaymentInfo(job),
            const SizedBox(height: 16),
            _buildQuoteCard(job),
            const SizedBox(height: 16),
            _buildExtraWorkCard(job),
            const SizedBox(height: 16),
            _buildEvidenceCard(job),
            const SizedBox(height: 16),
            _buildDisputeCard(job),
            const SizedBox(height: 16),
            _buildReworkCaseCard(job),
            const SizedBox(height: 16),
            _buildDisputeHistoryCard(),
            const SizedBox(height: 16),
            if (_canShareLocation(job))
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: AirwayColors.primarySoft,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Icon(Icons.location_on_outlined, size: 18),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            AirwayText.tr(
                              'Share your live location with this booking’s customer while this job screen is open. Sharing pauses in the background and stops when the job ends. This is optional.',
                              'इस जॉब स्क्रीन के खुले रहने तक अपनी लाइव लोकेशन इस बुकिंग के ग्राहक के साथ साझा करें। बैकग्राउंड में शेयरिंग रुक जाती है और जॉब खत्म होने पर बंद हो जाती है। यह वैकल्पिक है।',
                            ),
                            style: const TextStyle(fontSize: 12, height: 1.4),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(
                      AirwayText.tr(
                        'Customer visibility starts 30 minutes before the appointment. You can turn sharing off at any time.',
                        'ग्राहक को लोकेशन अपॉइंटमेंट से 30 मिनट पहले दिखेगी। आप कभी भी शेयरिंग बंद कर सकते हैं।',
                      ),
                      style: TextStyle(color: AirwayColors.textSecondary, fontSize: 11),
                    ),
                    Align(
                      alignment: Alignment.centerRight,
                      child: TextButton.icon(
                        onPressed: _locationConsentRequestInProgress
                            ? null
                            : () => _setLocationSharing(!_locationSharingEnabled),
                        icon: Icon(
                          _locationConsentRequestInProgress
                              ? Icons.hourglass_top_rounded
                              : _locationSharingEnabled
                                  ? Icons.location_off_outlined
                                  : Icons.my_location_rounded,
                        ),
                        label: Text(
                          _locationSharingEnabled
                              ? AirwayText.tr('Stop sharing', 'शेयरिंग बंद करें')
                              : AirwayText.tr('Share live location', 'लाइव लोकेशन साझा करें'),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            const SizedBox(height: 16),
            _buildActions(job),
          ],
        ),
      ),
    );
  }

  Widget _buildServiceInfo(WorkerAssignmentDetail job) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.book, color: AirwayColors.primary),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(job.serviceTitle, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                ),
              ],
            ),
            if (job.variantTitle?.isNotEmpty == true || job.quantity > 1) ...[
              const SizedBox(height: 8),
              Text(
                [
                  if (job.variantTitle?.isNotEmpty == true) job.variantTitle!,
                  job.serviceUnitLabel?.isNotEmpty == true
                      ? '${job.quantity} ${job.serviceUnitLabel}'
                      : 'Qty ${job.quantity}',
                ].join(' • '),
                style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12),
              ),
            ],
            if (job.customerAnswers.isNotEmpty) ...[
              const Divider(height: 22),
              Text(AirwayText.tr('Customer selections', 'ग्राहक के चयन'), style: TextStyle(fontWeight: FontWeight.w800)),
              const SizedBox(height: 6),
              for (final entry in job.customerAnswers.entries)
                if (!entry.key.endsWith('_id') &&
                    entry.key != 'vehicle_type' &&
                    entry.value != null && entry.value.toString().isNotEmpty)
                  Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Text(
                    workerCustomerAnswerLabel(entry.key, entry.value),
                    style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12),
                  ),
                ),
            ],
            if (job.formResponses.isNotEmpty) ...[
              const Divider(height: 22),
              Text(AirwayText.tr('Service details', 'सेवा का विवरण'), style: TextStyle(fontWeight: FontWeight.w800)),
              const SizedBox(height: 6),
              for (final answer in job.formResponses)
                Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '${answer['label'] ?? answer['key']}: ${answer['value']}',
                        style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12),
                      ),
                      if (answer['photo_url']?.toString().isNotEmpty == true)
                        Padding(
                          padding: const EdgeInsets.only(top: 7),
                          child: FutureBuilder<Map<String, String>>(
                            future: WorkerApi.getAuthHeaders(),
                            builder: (context, snapshot) {
                              if (!snapshot.hasData) {
                                return const SizedBox(height: 60, child: Center(child: CircularProgressIndicator()));
                              }
                              if (snapshot.hasError) return Text(AirwayText.tr('Could not authorize photo access.', 'फ़ोटो एक्सेस की अनुमति नहीं मिली।'));
                              return ClipRRect(
                                borderRadius: BorderRadius.circular(10),
                                child: Image.network(
                                  answer['photo_url'].toString(),
                                  headers: snapshot.data,
                                  height: 150,
                                  width: double.infinity,
                                  fit: BoxFit.cover,
                                  errorBuilder: (_, __, ___) => Text(AirwayText.tr('Photo is unavailable.', 'फ़ोटो उपलब्ध नहीं है।')),
                                ),
                              );
                            },
                          ),
                        ),
                    ],
                  ),
                ),
            ],
            if (job.addons.isNotEmpty) ...[
              const Divider(height: 22),
              Text(AirwayText.tr('Add-ons', 'अतिरिक्त सेवाएँ'), style: TextStyle(fontWeight: FontWeight.w800)),
              const SizedBox(height: 6),
              for (final addon in job.addons)
                Text(
                  '${addon['title']} × ${addon['quantity']}',
                  style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12),
                ),
            ],
            if (job.requiredMaterials.isNotEmpty) ...[
              const Divider(height: 22),
              Text(AirwayText.tr('Materials & tools to bring', 'साथ लाने वाली सामग्री और उपकरण'), style: const TextStyle(fontWeight: FontWeight.w800)),
              const SizedBox(height: 6),
              for (final item in job.requiredMaterials)
                Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Text('• $item', style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12)),
                ),
            ],
            if (job.notes?.isNotEmpty == true) ...[
              const Divider(height: 22),
              Text(AirwayText.tr('Customer note', 'ग्राहक का नोट'), style: TextStyle(fontWeight: FontWeight.w800)),
              const SizedBox(height: 6),
              Text(job.notes!, style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12)),
            ],
            if (job.issuePhotoUrl?.isNotEmpty == true) ...[
              const Divider(height: 22),
              Text(AirwayText.tr('Customer issue photo', 'ग्राहक द्वारा साझा की गई समस्या की फ़ोटो'), style: TextStyle(fontWeight: FontWeight.w800)),
              const SizedBox(height: 8),
              FutureBuilder<Map<String, String>>(
                future: WorkerApi.getAuthHeaders(),
                builder: (context, snapshot) {
                  if (snapshot.hasError) {
                    return Text(AirwayText.tr('Could not authorize photo access.', 'फ़ोटो एक्सेस की अनुमति नहीं मिली।'));
                  }
                  if (!snapshot.hasData) {
                    return const Center(child: CircularProgressIndicator());
                  }
                  return ClipRRect(
                    borderRadius: BorderRadius.circular(12),
                    child: Image.network(
                      job.issuePhotoUrl!,
                      headers: snapshot.data,
                      width: double.infinity,
                      height: 220,
                      fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) => Text(AirwayText.tr('Issue photo is unavailable.', 'समस्या की फ़ोटो उपलब्ध नहीं है।')),
                    ),
                  );
                },
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildScheduleInfo(WorkerAssignmentDetail job) {
    return Card(
      child: ListTile(
        leading: const Icon(Icons.event_available_rounded),
        title: Text(AirwayText.tr('Service appointment', 'सेवा का अपॉइंटमेंट')),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(AirwayText.tr('Service time: ${_formatDateTime(job.scheduledAt)}', 'सेवा का समय: ${_formatDateTime(job.scheduledAt)}')),
            if (job.recurringVisit != null) ...[
              const SizedBox(height: 4),
              Text(
                'Recurring Car Wash • Visit #${job.recurringVisit!['visit_number'] ?? ''}',
                style: const TextStyle(fontWeight: FontWeight.w700, color: AirwayColors.primary),
              ),
              const SizedBox(height: 2),
              Text(AirwayText.tr('Prepaid under plan #${job.recurringVisit!['plan_id'] ?? ''}', 'प्लान #${job.recurringVisit!['plan_id'] ?? ''} के अंतर्गत प्रीपेड')),
            ],
            if (job.dropScheduledAt != null) ...[
              const SizedBox(height: 4),
              Text(AirwayText.tr('Expected drop-off: ${_formatDateTime(job.dropScheduledAt!)}', 'अपेक्षित ड्रॉप-ऑफ़: ${_formatDateTime(job.dropScheduledAt!)}')),
            ],
          ],
        ),
        trailing: Icon(job.dropScheduledAt != null ? Icons.inventory_2 : Icons.schedule),
      ),
    );
  }

  Future<void> _openCustomerContact(WorkerAssignmentDetail job, {required bool message}) async {
    final phone = job.customerPhone;
    if (!job.customerContactAvailable || phone == null || phone.isEmpty) return;
    final uri = Uri(scheme: message ? 'sms' : 'tel', path: phone);
    final opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!opened && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Could not open the phone app.', 'फोन ऐप नहीं खुल सका।'))),
      );
    }
  }

  Future<void> _openCustomerMap(WorkerAssignmentDetail job) async {
    final latitude = job.addressLatitude;
    final longitude = job.addressLongitude;
    final query = latitude != null && longitude != null
        ? '$latitude,$longitude'
        : (job.address?.trim() ?? '');
    if (query.isEmpty) return;
    final uri = Uri.https('www.google.com', '/maps/search/', {'api': '1', 'query': query});
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }

  Widget _buildCustomerInfo(WorkerAssignmentDetail job) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            const Icon(Icons.person_outline_rounded, color: AirwayColors.primary),
            const SizedBox(width: 10),
            Expanded(child: Text(job.customerName, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800))),
          ]),
          const SizedBox(height: 10),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(color: const Color(0xFFEAF7EF), borderRadius: BorderRadius.circular(12)),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(AirwayText.tr('YOUR FIXED EARNING', 'आपकी तय कमाई'), style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w900, color: Color(0xFF267747))),
              const SizedBox(height: 3),
              Text(job.workerPayout == null ? AirwayText.tr('Not available', 'उपलब्ध नहीं') : '₹${job.workerPayout!.toStringAsFixed(2)}', style: const TextStyle(fontSize: 23, fontWeight: FontWeight.w900, color: Color(0xFF176B3A))),
              Text(AirwayText.tr('This amount is locked for this job and is settled after service completion.', 'यह राशि इस जॉब के लिए तय है और सेवा पूरी होने के बाद सेटल होगी।'), style: const TextStyle(fontSize: 11, color: Color(0xFF5D6F62))),
            ]),
          ),
          const SizedBox(height: 10),
          if (job.customerContactAvailable && job.customerPhone != null) ...[
            Row(children: [
              Expanded(child: OutlinedButton.icon(
                onPressed: () => _openCustomerContact(job, message: false),
                icon: const Icon(Icons.call_rounded),
                label: Text(AirwayText.tr('Call customer', 'ग्राहक को कॉल करें')),
              )),
              const SizedBox(width: 8),
              Expanded(child: FilledButton.icon(
                onPressed: () => _openCustomerContact(job, message: true),
                icon: const Icon(Icons.sms_rounded),
                label: Text(AirwayText.tr('Message', 'मैसेज')),
              )),
            ]),
          ] else if (job.customerContactAvailableAt != null) ...[
            Text(
              AirwayText.tr('Call and message unlock one hour before the appointment: ${_formatDateTime(job.customerContactAvailableAt!)}', 'कॉल और मैसेज अपॉइंटमेंट से एक घंटे पहले उपलब्ध होंगे: ${_formatDateTime(job.customerContactAvailableAt!)}'),
              style: const TextStyle(fontSize: 12, color: AirwayColors.textSecondary),
            ),
          ] else if (job.assignment.acceptedAt == null) ...[
            Text(
              AirwayText.tr('Accept this job to view the exact customer address. Call and SMS unlock one hour before the appointment.', 'ग्राहक का पूरा पता देखने के लिए जॉब स्वीकार करें। कॉल और SMS अपॉइंटमेंट से एक घंटे पहले उपलब्ध होंगे।'),
              style: const TextStyle(fontSize: 12, color: AirwayColors.textSecondary),
            ),
          ],
          if (job.address?.isNotEmpty == true) ...[
            const SizedBox(height: 8),
            Text(job.address!, style: const TextStyle(fontSize: 12, height: 1.4)),
            Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: () => _openCustomerMap(job),
                  icon: const Icon(Icons.directions_rounded),
                  label: Text(AirwayText.tr('Open location in Maps', 'Maps में लोकेशन खोलें')),
                ),
              ),
          ],
        ]),
      ),
    );
  }

  Widget _buildAssignmentInfo(WorkerAssignmentDetail job) {
    final assignment = job.assignment;

    return Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ListTile(
            leading: const Icon(Icons.people),
            title: Text(AirwayText.tr('Assignment', 'असाइनमेंट')),
            subtitle: Text(
              'Assigned: ${_formatDateTimeIfNotNull(assignment.assignedAt)}',
            ),
            trailing: Chip(
              label: Text(assignment.statusDisplay),
              backgroundColor: _getStatusColor(assignment.statusDisplay),
            ),
          ),
          if (job.address != null && job.address!.isNotEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Text(
                'Address: ${job.address}',
                style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildPaymentInfo(WorkerAssignmentDetail job) {
    final status = job.status;
    final isCompleted = status == BookingStatus.completed;
    final paymentLabel = job.paymentLabel ??
        (isCompleted ? 'Service completion verified.' : 'Payment status unavailable.');
    final statusLabel = isCompleted ? 'Completion verified' : 'Advance / payment';
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.payment),
              title: Text(AirwayText.tr('Payment', 'भुगतान')),
              subtitle: Text(paymentLabel),
              trailing: Chip(
                label: Text(statusLabel),
                backgroundColor: isCompleted ? Colors.green.shade100 : Colors.orange.shade100,
              ),
            ),
            if (isCompleted) ...[
              const SizedBox(height: 8),
              OutlinedButton.icon(
                onPressed: _isActionInProgress ? null : () => _recordCashReceived(job),
                icon: const Icon(Icons.payments_outlined),
                label: Text(AirwayText.tr('Cash received', 'नकद मिल गया')),
              ),
              Text(
                AirwayText.tr(
                  'Use only after receiving the balance in cash. Online-paid or multi-worker appointments cannot be settled here.',
                  'केवल बाकी राशि नकद मिलने के बाद उपयोग करें। ऑनलाइन भुगतान या कई वर्कर वाले अपॉइंटमेंट यहाँ से सेटल नहीं होंगे।',
                ),
                style: const TextStyle(fontSize: 11, color: AirwayColors.textSecondary),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildQuoteCard(WorkerAssignmentDetail job) {
    final quote = job.quote;
    if (quote == null && !job.canSubmitQuote) return const SizedBox.shrink();
    final quoteStatus = quote?['status']?.toString() ?? '';
    final lineItems = (quote?['line_items'] as List? ?? [])
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(AirwayText.tr('Inspection estimate', 'निरीक्षण का अनुमान'), style: TextStyle(fontWeight: FontWeight.w900, fontSize: 16)),
            if (quote != null) ...[
              const SizedBox(height: 8),
              Text('Quote v${quote['version']} • ${quoteStatus.replaceAll('_', ' ')}',
                  style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12)),
              const SizedBox(height: 8),
              for (final item in lineItems)
                Padding(
                  padding: const EdgeInsets.only(bottom: 5),
                  child: Row(children: [
                    Expanded(child: Text('${item['description']} (${item['type']})',
                        style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12))),
                    Text('₹${item['line_total'] ?? '0'}',
                        style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 12)),
                  ]),
                ),
              const Divider(height: 18),
              Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
                Text(AirwayText.tr('Estimate including tax', 'टैक्स सहित अनुमान'), style: TextStyle(fontWeight: FontWeight.w800)),
                Text('₹${quote['total_amount'] ?? '0'}',
                    style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 17)),
              ]),
              if (quote['notes']?.toString().isNotEmpty == true) ...[
                const SizedBox(height: 7),
                Text(quote['notes'].toString(),
                    style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12)),
              ],
              if (quoteStatus == 'pending_customer') ...[
                const SizedBox(height: 8),
                Text(AirwayText.tr('Waiting for the customer to approve or request a revision.', 'ग्राहक की स्वीकृति या संशोधन अनुरोध की प्रतीक्षा है।'),
                    style: TextStyle(color: AirwayColors.primary, fontWeight: FontWeight.w700, fontSize: 12)),
              ],
              if (quote?['worker_payout_amount'] != null) ...[
                const SizedBox(height: 6),
                Text('Your configured earning: ₹${quote!['worker_payout_amount']}',
                    style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 12)),
              ],
              if (quoteStatus == 'accepted' && quote?['repair_payment_status'] != 'paid') ...[
                const SizedBox(height: 8),
                Text(AirwayText.tr('Waiting for the customer’s remaining payment. Do not begin repair yet.', 'ग्राहक के बाकी भुगतान की प्रतीक्षा करें। अभी मरम्मत शुरू न करें।'),
                    style: const TextStyle(color: Colors.orange, fontWeight: FontWeight.w700, fontSize: 12)),
              ],
              if (quoteStatus == 'accepted' && quote?['repair_payment_status'] == 'paid' && quote?['repair_started_at'] == null) ...[
                const SizedBox(height: 10),
                SizedBox(width: double.infinity, child: FilledButton.icon(
                  onPressed: _isActionInProgress ? null : () => _startApprovedRepair(job),
                  icon: const Icon(Icons.build_circle_outlined),
                  label: Text(AirwayText.tr('Start repair', 'मरम्मत शुरू करें')),
                )),
              ],
              if (quoteStatus == 'accepted' && quote?['repair_started_at'] != null) ...[
                const SizedBox(height: 8),
                Text(AirwayText.tr('Repair started after payment confirmation.', 'भुगतान की पुष्टि के बाद मरम्मत शुरू हो गई है।'),
                    style: const TextStyle(color: Colors.green, fontWeight: FontWeight.w700, fontSize: 12)),
              ],
              if (quoteStatus == 'rejected' && quote?['customer_response_note']?.toString().isNotEmpty == true) ...[
                const SizedBox(height: 8),
                Text('Customer feedback: ${quote!['customer_response_note']}',
                    style: const TextStyle(color: Colors.deepOrange, fontSize: 12)),
              ],
            ],
            if (job.canSubmitQuote) ...[
              const SizedBox(height: 10),
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: _isActionInProgress ? null : () => _submitInspectionQuote(job),
                  icon: const Icon(Icons.request_quote_outlined),
                  label: Text(
                    quoteStatus == 'rejected' || quoteStatus == 'expired'
                        ? 'Submit revised estimate'
                        : 'Prepare estimate',
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Future<void> _submitInspectionQuote(WorkerAssignmentDetail job) async {
    final options = job.inspectionOptions;
    if (options.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(AirwayText.tr(
          'No repair rates are configured for this service yet. Contact AIRway support.',
          'इस सेवा के लिए मरम्मत की दरें अभी कॉन्फ़िगर नहीं हैं। AIRway सहायता से संपर्क करें।',
        )),
      ));
      return;
    }

    final selected = <int, int>{};
    final result = await showDialog<Map<int, int>>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (dialogContext, setDialogState) => AlertDialog(
          title: Text(AirwayText.tr('Select inspection findings', 'निरीक्षण में मिली समस्याएँ चुनें')),
          content: SizedBox(
            width: double.maxFinite,
            height: 440,
            child: ListView(
              children: [
                Text(AirwayText.tr(
                  'Select the work and parts actually required. AIRway prices are fixed; you can only set quantities.',
                  'वास्तव में आवश्यक काम और पार्ट चुनें। AIRway की कीमत तय है; आप केवल मात्रा चुन सकते हैं।',
                ), style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12)),
                const SizedBox(height: 10),
                for (final option in options) ...[
                  CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    value: selected.containsKey(option['id'] as int),
                    onChanged: (checked) => setDialogState(() {
                      final id = option['id'] as int;
                      if (checked == true) {
                        selected[id] = 1;
                      } else {
                        selected.remove(id);
                      }
                    }),
                    title: Text(option['title']?.toString() ?? ''),
                    subtitle: Text(
                      '${option['type']} • ₹${option['customer_price']}${(option['description']?.toString().isNotEmpty ?? false) ? ' • ${option['description']}' : ''}',
                      style: const TextStyle(fontSize: 12),
                    ),
                  ),
                  if (selected.containsKey(option['id'] as int))
                    Padding(
                      padding: const EdgeInsets.only(left: 42, bottom: 8),
                      child: Row(children: [
                        Text(AirwayText.tr('Quantity', 'मात्रा')),
                        const SizedBox(width: 12),
                        DropdownButton<int>(
                          value: selected[option['id'] as int],
                          items: List.generate(10, (index) => DropdownMenuItem(
                            value: index + 1,
                            child: Text('${index + 1}'),
                          )),
                          onChanged: (value) => setDialogState(() {
                            if (value != null) selected[option['id'] as int] = value;
                          }),
                        ),
                      ]),
                    ),
                  const Divider(height: 8),
                ],
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dialogContext), child: Text(AirwayText.tr('Cancel', 'रद्द करें'))),
            FilledButton(
              onPressed: selected.isEmpty ? null : () => Navigator.pop(dialogContext, Map<int, int>.from(selected)),
              child: Text(AirwayText.tr('Send estimate', 'अनुमान भेजें')),
            ),
          ],
        ),
      ),
    );
    if (result == null || !mounted) return;

    setState(() => _isActionInProgress = true);
    try {
      await WorkerApi.submitInspectionQuote(
        job.assignmentId,
        items: result.entries.map((entry) => {
          'rate_id': entry.key,
          'quantity': entry.value,
        }).toList(),
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(AirwayText.tr('Configured estimate sent directly to the customer.', 'कॉन्फ़िगर किया गया अनुमान सीधे ग्राहक को भेज दिया गया है।')),
      ));
      await _loadAssignedJob();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(AirwayText.tr('Could not submit estimate: $e', 'अनुमान भेजा नहीं जा सका: $e')),
        ));
      }
    } finally {
      if (mounted) setState(() => _isActionInProgress = false);
    }
  }

  Future<void> _startApprovedRepair(WorkerAssignmentDetail job) async {
    if (_isActionInProgress) return;
    setState(() => _isActionInProgress = true);
    try {
      await WorkerApi.startRepair(job.assignmentId);
      await _loadAssignedJob();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(AirwayText.tr('Payment verified. You can start the repair.', 'भुगतान सत्यापित हो गया। अब मरम्मत शुरू कर सकते हैं।')),
      ));
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(AirwayText.tr('Repair cannot start yet: $e', 'मरम्मत अभी शुरू नहीं हो सकती: $e')),
        ));
      }
    } finally {
      if (mounted) setState(() => _isActionInProgress = false);
    }
  }


  Widget _buildEvidenceCard(WorkerAssignmentDetail job) {
    if (job.workEvidence.isEmpty && job.status != BookingStatus.inProgress) {
      return const SizedBox.shrink();
    }
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(AirwayText.tr('Work photos', 'काम की फ़ोटो'), style: TextStyle(fontWeight: FontWeight.w900, fontSize: 16)),
            const SizedBox(height: 6),
            Text(AirwayText.tr('Capture the service condition before work and the completed result after work.', 'काम शुरू होने से पहले और पूरा होने के बाद सेवा की स्थिति की फ़ोटो लें।'),
                style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12)),
            for (final stage in ['before', 'after']) ...[
              const SizedBox(height: 12),
              Text(stage == 'before' ? 'Before work' : 'After work',
                  style: const TextStyle(fontWeight: FontWeight.w800)),
              const SizedBox(height: 7),
              for (final evidence in job.workEvidence.where((row) => row['stage'] == stage))
                Padding(
                  padding: const EdgeInsets.only(bottom: 9),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (evidence['note']?.toString().isNotEmpty == true)
                        Text(evidence['note'].toString(), style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12)),
                      FutureBuilder<Map<String, String>>(
                        future: WorkerApi.getAuthHeaders(),
                        builder: (context, snapshot) {
                          if (!snapshot.hasData) return const SizedBox(height: 70, child: Center(child: CircularProgressIndicator()));
                          if (snapshot.hasError) return Text(AirwayText.tr('Could not authorize evidence photo.', 'सबूत की फ़ोटो के लिए अनुमति नहीं मिली।'));
                          return ClipRRect(
                            borderRadius: BorderRadius.circular(10),
                            child: Image.network(
                              evidence['photo_url'].toString(),
                              headers: snapshot.data,
                              height: 150,
                              width: double.infinity,
                              fit: BoxFit.cover,
                              errorBuilder: (_, __, ___) => Text(AirwayText.tr('Evidence photo unavailable.', 'सबूत की फ़ोटो उपलब्ध नहीं है।')),
                            ),
                          );
                        },
                      ),
                    ],
                  ),
                ),
              if (job.status == BookingStatus.inProgress)
                Align(
                  alignment: Alignment.centerLeft,
                  child: OutlinedButton.icon(
                    onPressed: _isActionInProgress ? null : () => _addWorkEvidence(job, stage),
                    icon: const Icon(Icons.add_a_photo_outlined),
                    label: Text(stage == 'before' ? 'Add before photo' : 'Add after photo'),
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }

  Future<void> _addWorkEvidence(WorkerAssignmentDetail job, String stage) async {
    final source = await showModalBottomSheet<ImageSource>(
      context: context,
      builder: (sheetContext) => SafeArea(
        child: Wrap(children: [
          ListTile(
            leading: const Icon(Icons.camera_alt_outlined),
            title: Text(AirwayText.tr('Take photo', 'फ़ोटो लें')),
            onTap: () => Navigator.pop(sheetContext, ImageSource.camera),
          ),
          ListTile(
            leading: const Icon(Icons.photo_library_outlined),
            title: Text(AirwayText.tr('Choose from gallery', 'गैलरी से चुनें')),
            onTap: () => Navigator.pop(sheetContext, ImageSource.gallery),
          ),
        ]),
      ),
    );
    if (source == null || !mounted) return;
    final picked = await ImagePicker().pickImage(
      source: source,
      imageQuality: 82,
      maxWidth: 1600,
      maxHeight: 1600,
    );
    if (picked == null || !mounted) return;
    setState(() => _isActionInProgress = true);
    try {
      await WorkerApi.uploadJobEvidence(
        job.assignmentId,
        stage: stage,
        photo: File(picked.path),
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(stage == 'before' ? 'Before-work photo saved.' : 'After-work photo saved.'),
      ));
      await _loadAssignedJob();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(AirwayText.tr('Could not upload work photo: $e', 'काम की फ़ोटो अपलोड नहीं हो सकी: $e'))));
      }
    } finally {
      if (mounted) setState(() => _isActionInProgress = false);
    }
  }

  Widget _buildActions(WorkerAssignmentDetail job) {
    final status = job.status;

    if (status == BookingStatus.assigned || status == BookingStatus.confirmed) {
      return SizedBox(
        width: double.infinity,
        child: FilledButton.icon(
          onPressed: _isActionInProgress ? null : _startJob,
          icon: _isActionInProgress
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.play_arrow_rounded),
          label: Text(_isActionInProgress ? 'Starting...' : 'Start Job'),
        ),
      );
    }

    if (status == BookingStatus.inProgress) {
      return Row(
        children: [
          Expanded(
            child: OutlinedButton.icon(
              onPressed: _isActionInProgress ? null : () => _completeJob(),
              icon: _isActionInProgress
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.check),
              label: _isActionInProgress
                  ? Text(AirwayText.tr('Completing...', 'पूरा किया जा रहा है...'))
                  : Text(AirwayText.tr('Complete Job', 'काम पूरा करें')),
            ),
          ),
        ],
      );
    }

    if (status == BookingStatus.completed) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Card(
            child: ListTile(
              leading: Icon(Icons.check_circle),
              title: Text(AirwayText.tr('Job Status', 'जॉब की स्थिति')),
              subtitle: Text(AirwayText.tr('This job has been completed', 'यह जॉब पूरी हो चुकी है')),
            ),
          ),
          const SizedBox(height: 8),
          if (_hasRatedCustomer)
            const Text(
              'Thank you. Your customer feedback has been recorded.',
              textAlign: TextAlign.center,
              style: TextStyle(color: AirwayColors.success, fontWeight: FontWeight.w700),
            )
          else
            OutlinedButton.icon(
              onPressed: _isActionInProgress ? null : () => _rateCustomer(job),
              icon: const Icon(Icons.star_rounded),
              label: Text(AirwayText.tr('Rate customer', 'ग्राहक को रेट करें')),
            ),
        ],
      );
    }

    if (status == BookingStatus.confirmed) {
      return Card(
        child: ListTile(
          leading: const Icon(Icons.pending_outlined),
          title: Text(AirwayText.tr('Job Status', 'जॉब की स्थिति')),
          subtitle: Text(AirwayText.tr('Payment pending - awaiting worker assignment', 'भुगतान लंबित है - वर्कर असाइन होने की प्रतीक्षा है')),
        ),
      );
    }

    return Card(
      child: ListTile(
        leading: const Icon(Icons.info),
        title: Text(AirwayText.tr('Job Status', 'जॉब की स्थिति')),
        subtitle: Text(AirwayText.tr('Status: ${BookingStatus.display(status)}', 'स्थिति: ${BookingStatus.display(status)}')),
      ),
    );
  }

  Future<void> _rateCustomer(WorkerAssignmentDetail job) async {
    var selectedRating = 5;
    final commentController = TextEditingController();
    final result = await showDialog<({int rating, String comment})>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (dialogContext, setDialogState) => AlertDialog(
          title: Text(AirwayText.tr('Rate customer', 'ग्राहक को रेट करें')),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(AirwayText.tr('Share your experience working with this customer.', 'इस ग्राहक के साथ काम करने का अपना अनुभव साझा करें।')),
              const SizedBox(height: 12),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: List.generate(5, (index) => IconButton(
                  onPressed: () => setDialogState(() => selectedRating = index + 1),
                  icon: Icon(
                    index < selectedRating ? Icons.star_rounded : Icons.star_outline_rounded,
                    color: const Color(0xFFFFB020),
                    size: 30,
                  ),
                )),
              ),
              TextField(
                controller: commentController,
                maxLength: 500,
                maxLines: 3,
                decoration: InputDecoration(
                  labelText: AirwayText.tr('Comment (optional)', 'टिप्पणी (वैकल्पिक)'),
                  border: OutlineInputBorder(),
                ),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dialogContext), child: Text(AirwayText.tr('Not now', 'अभी नहीं'))),
            FilledButton(
              onPressed: () => Navigator.pop(
                dialogContext,
                (rating: selectedRating, comment: commentController.text.trim()),
              ),
              child: Text(AirwayText.tr('Submit rating', 'रेटिंग भेजें')),
            ),
          ],
        ),
      ),
    );
    commentController.dispose();
    if (result == null || !mounted) return;
    setState(() => _isActionInProgress = true);
    try {
      await RatingApi.submitRating(
        bookingId: job.bookingId,
        rating: result.rating,
        ratingType: 'worker',
        comment: result.comment,
      );
      if (!mounted) return;
      setState(() => _hasRatedCustomer = true);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Customer rating submitted. Thank you.', 'ग्राहक की रेटिंग भेज दी गई। धन्यवाद।'))),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Could not submit rating: $e', 'रेटिंग भेजी नहीं जा सकी: $e'))),
      );
    } finally {
      if (mounted) setState(() => _isActionInProgress = false);
    }
  }

  Color _getStatusColor(String status) {
    switch (status) {
      case 'Completed':
        return Colors.green.shade800;
      case 'In Progress':
        return Colors.blue.shade800;
      case 'Accepted':
      case 'Assigned':
        return Colors.orange.shade800;
      default:
        return Colors.grey.shade800;
    }
  }

  String _formatDateTime(DateTime dt) {
    return DateFormat('dd/MM/yyyy HH:mm').format(dt);
  }

  String _formatDateTimeIfNotNull(DateTime? dt) {
    if (dt == null) return 'Not assigned';
    return DateFormat('dd/MM/yyyy HH:mm').format(dt);
  }

  Widget _errorWidget(String message) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, color: Colors.redAccent, size: 52),
            const SizedBox(height: 14),
            Text(message,
                textAlign: TextAlign.center,
                style: const TextStyle(color: AirwayColors.textSecondary)),
            const SizedBox(height: 20),
            FilledButton(onPressed: _loadAssignedJob, child: Text(AirwayText.tr('Retry', 'फिर कोशिश करें'))),
          ],
        ),
      ),
    );
  }
}