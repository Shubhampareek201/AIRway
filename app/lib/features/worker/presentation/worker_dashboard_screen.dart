import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/worker/presentation/job_offers_screen.dart';
import 'package:airway/features/worker/presentation/assigned_job_screen.dart';
import 'package:airway/features/booking/data/booking_models.dart';
import 'package:airway/features/worker/data/worker_models.dart';
import 'package:airway/features/worker/data/worker_api.dart';

class WorkerDashboardScreen extends StatefulWidget {
  const WorkerDashboardScreen({super.key});

  @override
  State<WorkerDashboardScreen> createState() => _WorkerDashboardScreenState();
}

class _WorkerDashboardScreenState extends State<WorkerDashboardScreen> {
  WorkerProfile? _profile;
  Booking? _assignedJob;
  List<WorkerOffer> _offers = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadAll();
  }

  Future<void> _loadAll() async {
    if (mounted) setState(() { _loading = true; _error = null; });
    try {
      final profile = await WorkerApi.getMyProfile();
      final offers = await WorkerApi.getJobOffers();

      await Future.delayed(Duration.zero);

      if (mounted) {
        setState(() {
          _profile = profile;
          _offers = offers;
          if (profile.status != 'approved') {
            _error = 'Your worker profile is ${profile.status}. Contact support.';
          }
        });

        if (_offers.isNotEmpty) {
          for (final offer in offers) {
            if (_isOfferAssigned(offer)) {
              _assignedJob = await _loadBookingFromOffer(offer);
            }
          }
        }
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = 'Could not load dashboard. Check connection.';
        });
      }
    } finally {
      if (mounted) setState(() { _loading = false; });
    }
  }

  bool _isOfferAssigned(WorkerOffer offer) {
    return offer.status == WorkerOffer.accepted ||
        offer.status == WorkerOffer.pending && _hasAssignment();
  }

  bool _hasAssignment() {
    return false;
  }

  Future<Booking?> _loadBookingFromOffer(WorkerOffer offer) async {
    try {
      return await WorkerApi.startJob(offer.bookingId);
    } catch (e) {
      return null;
    }
  }

  Future<void> _refresh() async {
    await _loadAll();
  }

  void _navigateToOffers() {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (context) => const JobOffersScreen()),
    );
  }

  void _navigateToAssignedJob() {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (context) => const AssignedJobScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }

    if (_error != null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Worker Dashboard')),
        body: SafeArea(
          child: Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.warning_amber_rounded, size: 48, color: AirwayColors.error),
                  const SizedBox(height: 16),
                  Text(_error!, style: const TextStyle(fontSize: 16)),
                  const SizedBox(height: 16),
                  FilledButton(onPressed: _refresh, child: const Text('Retry')),
                ],
              ),
            ),
          ),
        ),
      );
    }

    final profile = _profile;
    if (profile == null) {
      return const Scaffold(
        body: Center(child: Text('No profile data available')),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Worker Dashboard'),
        actions: [
          IconButton(onPressed: _refresh, icon: const Icon(Icons.refresh)),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _buildProfileHeader(profile),
            const SizedBox(height: 16),
            _buildStatusCard(profile),
            const SizedBox(height: 16),
            _buildAssignedJobSection(),
            const SizedBox(height: 16),
            _buildPendingOffersSection(),
          ],
        ),
      ),
    );
  }

  Widget _buildProfileHeader(WorkerProfile profile) {
    return Card(
      child: ListTile(
        leading: CircleAvatar(
          radius: 24,
          backgroundColor: AirwayColors.primary,
          child: const Icon(Icons.work, color: Colors.white, size: 28),
        ),
        title: Text(profile.name ?? profile.phone ?? 'Worker'),
        subtitle: Text(profile.phone ?? ''),
        trailing: IconButton(
          icon: const Icon(Icons.info_outline),
          onPressed: () {
            showDialog(
              context: context,
              builder: (context) => AlertDialog(
                title: const Text('Profile Status'),
                content: Text('Status: ${profile.status}\n'
                    'UPI: ${profile.upiId ?? 'Not set'}\n'
                    'Experience: ${profile.experienceYears ?? 0} years'),
                actions: [
                  TextButton(onPressed: () => Navigator.pop(context), child: const Text('OK')),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildStatusCard(WorkerProfile profile) {
    final isApproved = profile.status == 'approved';
    final isOnline = profile.isOnline && isApproved;

    return Card(
      color: isOnline ? Colors.green[50] : (isApproved ? Colors.blue[50] : Colors.orange[100]),
      child: ListTile(
        leading: Icon(
          isOnline ? Icons.wifi : (isApproved ? Icons.check_circle : Icons.pending),
          color: isOnline ? Colors.green : (isApproved ? Colors.blue : Colors.orange),
        ),
        title: Text(isOnline ? 'Online - Accepting jobs' : (isApproved ? 'Offline' : 'Pending Approval')),
        trailing: Switch(
          value: isOnline,
          onChanged: (value) {
            // Toggle online status - would need backend endpoint
          },
        ),
      ),
    );
  }

  Widget _buildAssignedJobSection() {
    if (_assignedJob == null) {
      return Card(
        child: ListTile(
          leading: const Icon(Icons.work_outlined),
          title: const Text('No Assigned Job'),
          subtitle: const Text('Accept an offer to see your job here'),
          trailing: TextButton(
            onPressed: _navigateToAssignedJob,
            child: const Text('Assigned Jobs'),
          ),
        ),
      );
    }

    final job = _assignedJob!;
    return Card(
      child: InkWell(
        onTap: _navigateToAssignedJob,
        child: ListTile(
          leading: const Icon(Icons.directions_car, color: AirwayColors.primary),
          title: const Text('Assigned Job'),
          subtitle: Text('${job.serviceTitle} scheduled for ${job.scheduledAtDisplay}'),
          trailing: PopupMenuButton<String>(
            onSelected: (value) {
              if (value == 'start') {
                _startJobFromDashboard(job);
              } else if (value == 'complete') {
                _completeJobFromDashboard(job);
              }
            },
            itemBuilder: (context) => [
              const PopupMenuItem(value: 'start', child: Text('Start Job')),
              const PopupMenuItem(value: 'complete', child: Text('Complete Job')),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildPendingOffersSection() {
    final hasOffers = _offers.where((o) => o.status == WorkerOffer.pending).isNotEmpty;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('Job Offers (${_offers.where((o) => o.status == WorkerOffer.pending).length})'),
            TextButton(onPressed: _navigateToOffers, child: const Text('View All')),
          ],
        ),
        const SizedBox(height: 8),
        if (!hasOffers)
          const Card(
            child: ListTile(
              leading: Icon(Icons.work_outlined),
              title: Text('No pending offers'),
              subtitle: Text('New offers will appear here'),
            ),
          )
        else
          ListView.builder(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: _offers.where((o) => o.status == WorkerOffer.pending).take(5).length,
            itemBuilder: (context, index) {
              final offer = _offers.where((o) => o.status == WorkerOffer.pending).elementAt(index);
              return _buildOfferCard(offer);
            },
          ),
      ],
    );
  }

  Widget _buildOfferCard(WorkerOffer offer) {
    return Card(
      child: ListTile(
        title: Text('Booking #${offer.bookingId}'),
        subtitle: Text('Offered at: ${_formatDateTime(offer.offeredAt)}'),
        trailing: OutlinedButton(
          onPressed: offer.canAccept ? () => _acceptOffer(offer.id) : null,
          child: const Text('Accept'),
        ),
        onTap: () {
          // Show offer details
        },
      ),
    );
  }

  Future<void> _acceptOffer(int offerId) async {
    try {
      await WorkerApi.acceptOffer(offerId);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Offer accepted!')),
        );
        _loadAll();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to accept: $e')),
        );
      }
    }
  }

  Future<void> _startJobFromDashboard(Booking job) async {
    if (!mounted) return;
    try {
      await WorkerApi.startJob(job.id);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Job started')),
        );
        _loadAll();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to start job: $e')),
        );
      }
    }
  }

  Future<void> _completeJobFromDashboard(Booking job) async {
    if (!mounted) return;
    try {
      await WorkerApi.completeJob(job.id);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Job completed')),
        );
        _loadAll();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to complete job: $e')),
        );
      }
    }
  }

  String _formatDateTime(DateTime dt) {
    return '${dt.day}/${dt.month}/${dt.year} ${dt.hour}:${dt.minute.toString().padLeft(2, '0')}';
  }
}