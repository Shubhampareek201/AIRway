import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:intl/intl.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/worker/data/worker_api.dart';
import 'package:airway/features/worker/data/worker_models.dart';
import 'package:airway/features/booking/data/booking_models.dart';
import 'package:airway/features/ratings/data/rating_api.dart';

class AssignedJobScreen extends StatefulWidget {
  const AssignedJobScreen({super.key, this.assignmentId});

  final int? assignmentId;

  @override
  State<AssignedJobScreen> createState() => _AssignedJobScreenState();
}

class _AssignedJobScreenState extends State<AssignedJobScreen> {
  WorkerAssignmentDetail? _jobDetail;
  bool _loading = true;
  String? _error;
  bool _isActionInProgress = false;
  bool _hasRatedCustomer = false;

  @override
  void initState() {
    super.initState();
    _loadAssignedJob();
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
        if (mounted) {
          setState(() {
            _error = 'This job is no longer assigned to your account.';
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
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = 'Could not load assigned job: $e';
          _loading = false;
        });
      }
    }
  }

  Future<void> _startJob() async {
    if (!mounted || _jobDetail == null) return;

    setState(() {
      _isActionInProgress = true;
    });

    try {
      await WorkerApi.startJob(_jobDetail!.assignmentId);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Job started')),
        );
        await _loadAssignedJob();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to start job: $e')),
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
        const SnackBar(
          content: Text('Ask the customer to share the 6-digit completion code shown in their AIRway notifications.'),
          duration: Duration(seconds: 5),
        ),
      );
      final controller = TextEditingController();
      final code = await showDialog<String>(
        context: context,
        barrierDismissible: false,
        builder: (dialogContext) => AlertDialog(
          title: const Text('Verify service completion'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Enter the 6-digit code shared by the customer after the service is finished.'),
              const SizedBox(height: 14),
              TextField(
                controller: controller,
                autofocus: true,
                keyboardType: TextInputType.number,
                maxLength: 6,
                decoration: const InputDecoration(
                  labelText: 'Customer completion code',
                  border: OutlineInputBorder(),
                  counterText: '',
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () {
                final value = controller.text.trim();
                if (RegExp(r'^[0-9]{6}$').hasMatch(value)) {
                  Navigator.pop(dialogContext, value);
                }
              },
              child: const Text('Verify & complete'),
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
          SnackBar(content: Text(result['detail']?.toString() ?? 'Completion verified.')),
        );
        await _loadAssignedJob();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Completion verification failed: $e')),
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
        appBar: AppBar(title: const Text('Assigned Job')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    if (_error != null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Assigned Job')),
        body: _errorWidget(_error!),
      );
    }

    if (_jobDetail == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Assigned Job')),
        body: const Center(child: Text('No assigned job')),
      );
    }

    final job = _jobDetail!;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Assigned Job'),
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
            _buildEvidenceCard(job),
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
              const Text('Customer selections', style: TextStyle(fontWeight: FontWeight.w800)),
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
              const Text('Service details', style: TextStyle(fontWeight: FontWeight.w800)),
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
                              if (snapshot.hasError) return const Text('Could not authorize photo access.');
                              return ClipRRect(
                                borderRadius: BorderRadius.circular(10),
                                child: Image.network(
                                  answer['photo_url'].toString(),
                                  headers: snapshot.data,
                                  height: 150,
                                  width: double.infinity,
                                  fit: BoxFit.cover,
                                  errorBuilder: (_, __, ___) => const Text('Photo is unavailable.'),
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
              const Text('Add-ons', style: TextStyle(fontWeight: FontWeight.w800)),
              const SizedBox(height: 6),
              for (final addon in job.addons)
                Text(
                  '${addon['title']} × ${addon['quantity']}',
                  style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12),
                ),
            ],
            if (job.notes?.isNotEmpty == true) ...[
              const Divider(height: 22),
              const Text('Customer note', style: TextStyle(fontWeight: FontWeight.w800)),
              const SizedBox(height: 6),
              Text(job.notes!, style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12)),
            ],
            if (job.issuePhotoUrl?.isNotEmpty == true) ...[
              const Divider(height: 22),
              const Text('Customer issue photo', style: TextStyle(fontWeight: FontWeight.w800)),
              const SizedBox(height: 8),
              FutureBuilder<Map<String, String>>(
                future: WorkerApi.getAuthHeaders(),
                builder: (context, snapshot) {
                  if (snapshot.hasError) {
                    return const Text('Could not authorize photo access.');
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
                      errorBuilder: (_, __, ___) => const Text('Issue photo is unavailable.'),
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
        leading: const Icon(Icons.schedule),
        title: const Text('Scheduled Time'),
        subtitle: Text(_formatDateTime(job.scheduledAt)),
        trailing: Icon(
          job.dropScheduledAt != null ? Icons.inventory_2 : Icons.schedule,
        ),
      ),
    );
  }

  Widget _buildCustomerInfo(WorkerAssignmentDetail job) {
    return Card(
      child: ListTile(
        leading: const Icon(Icons.person),
        title: Text(job.customerName),
        subtitle: const Text('Customer contact details are protected by AIRway.'),
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
            title: const Text('Assignment'),
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
        title: const Text('Payment'),
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
            const Text('Inspection estimate', style: TextStyle(fontWeight: FontWeight.w900, fontSize: 16)),
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
                const Text('Estimate including tax', style: TextStyle(fontWeight: FontWeight.w800)),
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
                const Text('Waiting for the customer to approve or request a revision.',
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
        title: const Text('Prepare inspection estimate'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Align(alignment: Alignment.centerLeft, child: Text('Labour')),
              TextField(controller: labourDescriptionController, decoration: const InputDecoration(labelText: 'Work description')),
              TextField(controller: labourController, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'Labour amount (₹)')),
              const SizedBox(height: 10),
              const Align(alignment: Alignment.centerLeft, child: Text('Materials')),
              TextField(controller: materialDescriptionController, decoration: const InputDecoration(labelText: 'Material description')),
              TextField(controller: materialController, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'Material amount (₹)')),
              const SizedBox(height: 10),
              const Align(alignment: Alignment.centerLeft, child: Text('Other')),
              TextField(controller: otherDescriptionController, decoration: const InputDecoration(labelText: 'Other work / charge')),
              TextField(controller: otherController, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'Other amount (₹)')),
              const SizedBox(height: 10),
              TextField(controller: notesController, maxLines: 3, maxLength: 500, decoration: const InputDecoration(labelText: 'Notes for customer')),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Cancel')),
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
            child: const Text('Review estimate'),
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
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Enter at least one positive estimate amount.')));
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
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Estimate sent to customer for approval.')));
      await _loadAssignedJob();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not submit estimate: $e')));
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
            const Text('Work photos', style: TextStyle(fontWeight: FontWeight.w900, fontSize: 16)),
            const SizedBox(height: 6),
            Text('Capture the service condition before work and the completed result after work.',
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
                          if (snapshot.hasError) return const Text('Could not authorize evidence photo.');
                          return ClipRRect(
                            borderRadius: BorderRadius.circular(10),
                            child: Image.network(
                              evidence['photo_url'].toString(),
                              headers: snapshot.data,
                              height: 150,
                              width: double.infinity,
                              fit: BoxFit.cover,
                              errorBuilder: (_, __, ___) => const Text('Evidence photo unavailable.'),
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
            title: const Text('Take photo'),
            onTap: () => Navigator.pop(sheetContext, ImageSource.camera),
          ),
          ListTile(
            leading: const Icon(Icons.photo_library_outlined),
            title: const Text('Choose from gallery'),
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
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not upload work photo: $e')));
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
                  ? const Text('Completing...')
                  : const Text('Complete Job'),
            ),
          ),
        ],
      );
    }

    if (status == BookingStatus.completed) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Card(
            child: ListTile(
              leading: Icon(Icons.check_circle),
              title: Text('Job Status'),
              subtitle: Text('This job has been completed'),
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
              label: const Text('Rate customer'),
            ),
        ],
      );
    }

    if (status == BookingStatus.confirmed) {
      return Card(
        child: const ListTile(
          leading: Icon(Icons.pending_outlined),
          title: Text('Job Status'),
          subtitle: Text('Payment pending - awaiting worker assignment'),
        ),
      );
    }

    return Card(
      child: ListTile(
        leading: const Icon(Icons.info),
        title: const Text('Job Status'),
        subtitle: Text('Status: ${BookingStatus.display(status)}'),
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
          title: const Text('Rate customer'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Share your experience working with this customer.'),
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
                decoration: const InputDecoration(
                  labelText: 'Comment (optional)',
                  border: OutlineInputBorder(),
                ),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Not now')),
            FilledButton(
              onPressed: () => Navigator.pop(
                dialogContext,
                (rating: selectedRating, comment: commentController.text.trim()),
              ),
              child: const Text('Submit rating'),
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
        const SnackBar(content: Text('Customer rating submitted. Thank you.')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not submit rating: $e')),
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
            FilledButton(onPressed: _loadAssignedJob, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }
}