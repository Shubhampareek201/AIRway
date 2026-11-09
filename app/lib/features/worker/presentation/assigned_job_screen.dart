import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/worker/data/worker_api.dart';
import 'package:airway/features/worker/data/worker_models.dart';
import 'package:airway/features/booking/data/booking_models.dart';

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
      if (mounted) {
        _jobDetail = WorkerAssignmentDetail.fromMap(detail);
        setState(() {
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

  Future<String?> _promptServiceOtp(String milestone) async {
    final controller = TextEditingController();
    final result = await showDialog<String>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) => AlertDialog(
        title: Text('Customer $milestone OTP'),
        content: TextField(
          controller: controller,
          autofocus: true,
          keyboardType: TextInputType.number,
          maxLength: 6,
          decoration: const InputDecoration(
            labelText: '6-digit OTP',
            helperText: 'Ask the customer to share the OTP for this service milestone.',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              final code = controller.text.trim();
              final valid = code.length == 6 &&
                  code.codeUnits.every((unit) => unit >= 48 && unit <= 57);
              if (valid) Navigator.pop(dialogContext, code);
            },
            child: const Text('Verify OTP'),
          ),
        ],
      ),
    );
    controller.dispose();
    return result;
  }

  Future<void> _startJob() async {
    if (!mounted || _jobDetail == null) return;
    final otp = _jobDetail!.requiresServiceOtp
        ? await _promptServiceOtp('start')
        : null;
    if (!mounted || (_jobDetail!.requiresServiceOtp && otp == null)) return;

    setState(() {
      _isActionInProgress = true;
    });

    try {
      await WorkerApi.startJob(_jobDetail!.assignmentId, otp: otp);
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
    final otp = _jobDetail!.requiresServiceOtp
        ? await _promptServiceOtp('completion')
        : null;
    if (!mounted || (_jobDetail!.requiresServiceOtp && otp == null)) return;

    setState(() {
      _isActionInProgress = true;
    });

    try {
      await WorkerApi.completeJob(_jobDetail!.assignmentId, otp: otp);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Job completed')),
        );
        await _loadAssignedJob();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to complete job: $e')),
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
                [if (job.variantTitle?.isNotEmpty == true) job.variantTitle!, 'Qty ${job.quantity}'].join(' • '),
                style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12),
              ),
            ],
            if (job.customerAnswers.isNotEmpty) ...[
              const Divider(height: 22),
              const Text('Customer selections', style: TextStyle(fontWeight: FontWeight.w800)),
              const SizedBox(height: 6),
              for (final entry in job.customerAnswers.entries)
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
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Text(
                    '${answer['label'] ?? answer['key']}: ${answer['value']}',
                    style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12),
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
        subtitle: Text(job.customerPhone ?? 'No phone'),
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

    // Check if payment is expected based on status
    final isPaid = status == BookingStatus.inProgress ||
        status == BookingStatus.completed ||
        status == BookingStatus.confirmed;

    return Card(
      child: ListTile(
        leading: const Icon(Icons.payment),
        title: const Text('Payment'),
        subtitle: isPaid
            ? const Text('Payment completed')
            : const Text('Payment pending'),
        trailing: Chip(
          label: Text(isPaid ? 'Paid' : 'Pending'),
          backgroundColor:
              isPaid ? Colors.green.shade100 : Colors.orange.shade100,
        ),
      ),
    );
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
      return Card(
        child: const ListTile(
          leading: Icon(Icons.check_circle),
          title: Text('Job Status'),
          subtitle: Text('This job has been completed'),
        ),
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
