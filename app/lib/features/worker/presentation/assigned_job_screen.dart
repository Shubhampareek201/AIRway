import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:geolocator/geolocator.dart';
import 'package:intl/intl.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/worker/data/worker_api.dart';
import 'package:airway/core/localization/airway_text.dart';
import 'package:airway/features/worker/data/worker_models.dart';
import 'package:airway/features/booking/data/booking_models.dart';
import 'package:airway/features/ratings/data/rating_api.dart';

class AssignedJobScreen extends StatefulWidget {
  const AssignedJobScreen({super.key, this.assignmentId});

  final int? assignmentId;

  @override
  State<AssignedJobScreen> createState() => _AssignedJobScreenState();
}

class _AssignedJobScreenState extends State<AssignedJobScreen> with WidgetsBindingObserver {
  WorkerAssignmentDetail? _jobDetail;
  bool _loading = true;
  String? _error;
  bool _isActionInProgress = false;
  bool _hasRatedCustomer = false;
  Timer? _locationTimer;
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
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && _jobDetail != null) {
      _locationPermissionBlocked = false;
      _configureLocationSharing(_jobDetail!);
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
        setState(() {
          _hasRatedCustomer = hasRatedCustomer;
          _locationSharingEnabled = parsedDetail.assignment.locationSharingEnabled;
          _loading = false;
        });
        _configureLocationSharing(parsedDetail);
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
      await WorkerApi.proposeExtraWork(
        job.bookingId,
        reason: proposal['reason']!,
        description: proposal['description']!,
        quantity: int.parse(proposal['quantity']!),
        unitPrice: proposal['unit_price']!,
        additionalDurationMinutes: int.parse(proposal['duration']!),
      );
      await _loadAssignedJob();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Extra-work request sent. Wait for customer approval before proceeding.')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not send extra-work request: ' + e.toString())));
    } finally {
      if (mounted) setState(() => _isActionInProgress = false);
    }
  }

  Widget _buildExtraWorkCard(WorkerAssignmentDetail job) {
    if (job.status != BookingStatus.inProgress) return const SizedBox.shrink();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Additional work', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
          const SizedBox(height: 6),
          const Text('If the customer needs work beyond the booked service, send a priced request. Do not start or charge for it until the customer approves.'),
          const SizedBox(height: 10),
          SizedBox(width: double.infinity, child: FilledButton.icon(
            onPressed: _isActionInProgress ? null : _proposeExtraWork,
            icon: const Icon(Icons.add_task_rounded),
            label: const Text('Request customer approval'),
          )),
        ]),
      ),
    );
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

  Widget _buildCustomerInfo(WorkerAssignmentDetail job) {
    return Card(
      child: ListTile(
        leading: const Icon(Icons.person),
        title: Text(job.customerName),
        subtitle: Text(
          job.paymentLabel ?? 'Customer contact details are protected by AIRway.',
          style: const TextStyle(fontSize: 12),
        ),
        trailing: Text(
          '₹${job.amount.toStringAsFixed(0)}',
          style: const TextStyle(fontWeight: FontWeight.bold),
        ),
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
      child: ListTile(
        leading: const Icon(Icons.payment),
        title: Text(AirwayText.tr('Payment', 'भुगतान')),
        subtitle: Text(paymentLabel),
        trailing: Chip(
          label: Text(statusLabel),
          backgroundColor: isCompleted ? Colors.green.shade100 : Colors.orange.shade100,
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
    final labourController = TextEditingController();
    final materialController = TextEditingController();
    final otherController = TextEditingController();
    final labourDescriptionController = TextEditingController(text: 'Labour and repair work');
    final materialDescriptionController = TextEditingController(text: 'Required materials and spare parts');
    final otherDescriptionController = TextEditingController(text: 'Additional charges');
    final notesController = TextEditingController();

    final result = await showDialog<Map<String, String>>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(AirwayText.tr('Prepare inspection estimate', 'निरीक्षण का अनुमान तैयार करें')),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Align(alignment: Alignment.centerLeft, child: Text(AirwayText.tr('Labour', 'मज़दूरी'))),
              TextField(controller: labourDescriptionController, decoration: InputDecoration(labelText: AirwayText.tr('Work description', 'काम का विवरण'))),
              TextField(controller: labourController, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: InputDecoration(labelText: AirwayText.tr('Labour amount (₹)', 'मज़दूरी की राशि (₹)'))),
              const SizedBox(height: 10),
              Align(alignment: Alignment.centerLeft, child: Text(AirwayText.tr('Materials', 'सामग्री'))),
              TextField(controller: materialDescriptionController, decoration: InputDecoration(labelText: AirwayText.tr('Material description', 'सामग्री का विवरण'))),
              TextField(controller: materialController, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: InputDecoration(labelText: AirwayText.tr('Material amount (₹)', 'सामग्री की राशि (₹)'))),
              const SizedBox(height: 10),
              Align(alignment: Alignment.centerLeft, child: Text(AirwayText.tr('Other', 'अन्य'))),
              TextField(controller: otherDescriptionController, decoration: InputDecoration(labelText: AirwayText.tr('Other work / charge', 'अन्य काम / शुल्क'))),
              TextField(controller: otherController, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: InputDecoration(labelText: AirwayText.tr('Other amount (₹)', 'अन्य राशि (₹)'))),
              const SizedBox(height: 10),
              TextField(controller: notesController, maxLines: 3, maxLength: 500, decoration: InputDecoration(labelText: AirwayText.tr('Notes for customer', 'ग्राहक के लिए नोट'))),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext), child: Text(AirwayText.tr('Cancel', 'रद्द करें'))),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, {
              'labour': labourController.text.trim(),
              'labour_description': labourDescriptionController.text.trim(),
              'material': materialController.text.trim(),
              'material_description': materialDescriptionController.text.trim(),
              'other': otherController.text.trim(),
              'other_description': otherDescriptionController.text.trim(),
              'notes': notesController.text.trim(),
            }),
            child: Text(AirwayText.tr('Review estimate', 'अनुमान की समीक्षा करें')),
          ),
        ],
      ),
    );
    labourController.dispose();
    materialController.dispose();
    otherController.dispose();
    labourDescriptionController.dispose();
    materialDescriptionController.dispose();
    otherDescriptionController.dispose();
    notesController.dispose();
    if (result == null || !mounted) return;

    final lineItems = <Map<String, dynamic>>[];
    void addLine(String type, String amountText, String description) {
      final value = double.tryParse(amountText);
      if (value != null && value > 0) {
        lineItems.add({
          'type': type,
          'description': description.isEmpty ? type : description,
          'quantity': '1',
          'unit_price': value.toStringAsFixed(2),
        });
      }
    }
    addLine('labour', result['labour'] ?? '', result['labour_description'] ?? '');
    addLine('material', result['material'] ?? '', result['material_description'] ?? '');
    addLine('other', result['other'] ?? '', result['other_description'] ?? '');
    if (lineItems.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(AirwayText.tr('Enter at least one positive estimate amount.', 'कम से कम एक सकारात्मक अनुमान राशि दर्ज करें।'))));
      return;
    }

    setState(() => _isActionInProgress = true);
    try {
      await WorkerApi.submitInspectionQuote(
        job.assignmentId,
        lineItems: lineItems,
        notes: result['notes'] ?? '',
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(AirwayText.tr('Estimate sent to customer for approval.', 'अनुमान ग्राहक की स्वीकृति के लिए भेज दिया गया है।'))));
      await _loadAssignedJob();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(AirwayText.tr('Could not submit estimate: $e', 'अनुमान भेजा नहीं जा सका: $e'))));
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