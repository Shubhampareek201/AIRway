import 'dart:io';
import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/worker/data/worker_app_api.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';
import 'package:image_picker/image_picker.dart';

enum WorkerApplicationStep { photo, services, zones, idDocument, review }

class WorkerApplicationScreen extends StatefulWidget {
  const WorkerApplicationScreen({super.key});

  @override
  State<WorkerApplicationScreen> createState() => _WorkerApplicationScreenState();
}

class _WorkerApplicationScreenState extends State<WorkerApplicationScreen> {
  WorkerApplicationStep _currentStep = WorkerApplicationStep.photo;

  List<Service> _services = [];
  List<dynamic> _zones = [];
  final List<int> _selectedServiceIds = [];
  final Map<int, Set<String>> _selectedServiceCapabilities = {};
  final Map<int, TextEditingController> _capabilityControllers = {};
  final List<int> _selectedZoneIds = [];
  int? _experienceYears;
  final TextEditingController _experienceController = TextEditingController();
  String? _bio;
  final TextEditingController _bioController = TextEditingController();
  final TextEditingController _nameController = TextEditingController();
  final TextEditingController _emailController = TextEditingController();
  final TextEditingController _qualificationController = TextEditingController();
  final TextEditingController _equipmentController = TextEditingController();
  final TextEditingController _addressController = TextEditingController();
  final TextEditingController _landmarkController = TextEditingController();
  final TextEditingController _upiController = TextEditingController();
  String _selectedGender = 'other';
  final Map<int, Map<String, String>> _weeklySchedule = {};

  File? _profilePhoto;
  File? _idDocument;
  String _selectedIdType = 'aadhaar';

  int? _existingExperienceYears;
  String? _existingBio;
  List<int> _existingServiceIds = [];
  List<int> _existingZoneIds = [];
  bool _idDocumentUploaded = false;
  bool _hasExistingPhoto = false;

  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadExistingApplication();
    _loadServicesAndZones();
    _bioController.text = _existingBio ?? '';
    _experienceController.text = _existingExperienceYears?.toString() ?? '';
  }

  @override
  void dispose() {
    _experienceController.dispose();
    _bioController.dispose();
    _nameController.dispose();
    _emailController.dispose();
    _qualificationController.dispose();
    _equipmentController.dispose();
    _addressController.dispose();
    _landmarkController.dispose();
    _upiController.dispose();
    for (final controller in _capabilityControllers.values) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _loadExistingApplication() async {
    try {
      final statusData = await WorkerAppApi.fetchWorkerApplicationStatus();
      if (statusData == null) return;

      _nameController.text = statusData['name']?.toString() ?? '';
      _emailController.text = statusData['email']?.toString() ?? '';

      final workerProfile = statusData['worker_profile'];
      if (workerProfile == null) {
        if (mounted) setState(() {});
        return;
      }

      // Check if there's already a PENDING application
      final status = workerProfile['status'];
      if (status != 'pending' && status != 'approved' && status != 'rejected') {
        return; // No existing application, user can start fresh
      }

      // Check if ID document was already uploaded (SECURITY: do NOT expose the document path)
      final idType = workerProfile['id_type'];
      _idDocumentUploaded = idType != null;

      // Mark that profile exists to show "Continue Application" in UI
      setState(() {
        _existingExperienceYears = workerProfile['experience_years'];
        _existingBio = workerProfile['bio'];
        _experienceYears = _existingExperienceYears;
        _bio = _existingBio;
        _selectedIdType = idType ?? 'aadhaar';
        final savedGender = workerProfile['gender']?.toString();
        if (savedGender == 'male' || savedGender == 'female' || savedGender == 'other') {
          _selectedGender = savedGender!;
        }
        _hasExistingPhoto = workerProfile['has_photo'] == true || workerProfile['photo_url'] != null;
        _qualificationController.text = workerProfile['qualification']?.toString() ?? '';
        _equipmentController.text = workerProfile['equipment_details']?.toString() ?? '';
        _addressController.text = workerProfile['residential_address']?.toString() ?? '';
        _landmarkController.text = workerProfile['landmark']?.toString() ?? '';
        _upiController.text = workerProfile['upi_id']?.toString() ?? '';
        _bioController.text = _existingBio ?? '';
        _experienceController.text = _existingExperienceYears?.toString() ?? '';
        final savedSchedule = workerProfile['schedule'];
        if (savedSchedule is Map) {
          for (final entry in savedSchedule.entries) {
            final day = int.tryParse(entry.key.toString());
            if (day != null && entry.value is Map) {
              final times = Map<String, dynamic>.from(entry.value as Map);
              _weeklySchedule[day] = {
                'start': times['start']?.toString() ?? '09:00',
                'end': times['end']?.toString() ?? '18:00',
              };
            }
          }
        }

        // Load existing services and zones
        final serviceIds = workerProfile['service_ids'] as List?;
        final zoneIds = workerProfile['zone_ids'] as List?;
        if (serviceIds != null) {
          _existingServiceIds = serviceIds.cast<int>();
          _selectedServiceIds.addAll(_existingServiceIds);
        }
        if (zoneIds != null) {
          _existingZoneIds = zoneIds.cast<int>();
          _selectedZoneIds.addAll(_existingZoneIds);
        }
      });

      // Navigate to appropriate step based on what's missing
      if (!_idDocumentUploaded) {
        // ID document missing - go to ID document step
        if (_selectedServiceIds.isNotEmpty && _selectedZoneIds.isNotEmpty) {
          // Services and zones already done, go to ID document
          if (mounted) {
            setState(() {
              _currentStep = WorkerApplicationStep.idDocument;
            });
          }
        }
      }
      // If ID document is already uploaded and profile is PENDING, user needs to wait for admin review
      // They can switch to Worker mode when profile is APPROVED
    } catch (e) {
      // Silent fail - user can start fresh
    }
  }

  Future<void> _loadServicesAndZones() async {
    if (!mounted) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final servicesResult = await WorkerAppApi.fetchServicesForWorkerApplication();
      final zonesResult = await WorkerAppApi.fetchZones();

      if (!mounted) return;
      setState(() {
        _services = List<Service>.from(servicesResult);
        _zones = zonesResult;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = 'Failed to load services/zones: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _pickPhoto() async {
    try {
      final picker = ImagePicker();
      final picked = await picker.pickImage(
        source: ImageSource.camera,
        imageQuality: 80,
        maxWidth: 800,
        maxHeight: 800,
      );
      if (picked != null && mounted) {
        setState(() => _profilePhoto = File(picked.path));
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to pick photo: $e')),
      );
    }
  }

  Future<void> _pickIdDocument() async {
    try {
      final picker = ImagePicker();
      final picked = await picker.pickImage(
        source: ImageSource.gallery,
        imageQuality: 80,
        maxWidth: 2000,
        maxHeight: 2000,
      );
      if (picked != null && mounted) {
        setState(() => _idDocument = File(picked.path));
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to pick document: $e')),
      );
    }
  }

  void _toggleService(int serviceId) {
    setState(() {
      if (_selectedServiceIds.contains(serviceId)) {
        _selectedServiceIds.removeWhere((id) => id == serviceId);
      } else {
        _selectedServiceIds.add(serviceId);
      }
    });
  }

  Map<int, List<String>> _buildServiceCapabilities() {
    final result = <int, List<String>>{};
    for (final serviceId in _selectedServiceIds) {
      final tasks = <String>{...?_selectedServiceCapabilities[serviceId]};
      final custom = _capabilityControllers[serviceId]?.text
              .split(",")
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty) ??
          const <String>[];
      tasks.addAll(custom);
      result[serviceId] = tasks.toList();
    }
    return result;
  }

  void _toggleZone(int zoneId) {
    setState(() {
      if (_selectedZoneIds.contains(zoneId)) {
        _selectedZoneIds.removeWhere((id) => id == zoneId);
      } else {
        _selectedZoneIds.add(zoneId);
      }
    });
  }

  Future<void> _submitApplication() async {
    if (!mounted) return;
    if (_profilePhoto == null && !_hasExistingPhoto) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Profile photo is required. Please take a photo first.')),
      );
      return;
    }
    if (_nameController.text.trim().isEmpty || _addressController.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please enter your full name and residential address.')),
      );
      return;
    }
    if (_weeklySchedule.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please select at least one working day and its hours.')),
      );
      return;
    }

    if (_selectedServiceIds.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please select at least one service.')),
      );
      return;
    }

    if (_selectedZoneIds.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please select at least one service zone.')),
      );
      return;
    }

    if (_idDocument == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please upload an ID document.')),
      );
      return;
    }

    setState(() { _loading = true; _error = null; });

    // First, try to submit the worker application
    try {
      await WorkerAppApi.submitWorkerApplication(
        serviceIds: _selectedServiceIds,
        serviceCapabilities: _buildServiceCapabilities(),
        zoneIds: _selectedZoneIds,
        experienceYears: int.tryParse(_experienceController.text),
        bio: _bioController.text.isEmpty ? null : _bioController.text,
        name: _nameController.text.trim(),
        email: _emailController.text.trim(),
        gender: _selectedGender,
        qualification: _qualificationController.text,
        equipmentDetails: _equipmentController.text,
        residentialAddress: _addressController.text.trim(),
        landmark: _landmarkController.text,
        upiId: _upiController.text,
        schedule: _weeklySchedule,
        profilePhoto: _profilePhoto,
      );

      if (!mounted) return;
      setState(() { _idDocumentUploaded = false; });

      // Application created successfully, now upload ID document
      await _uploadIdDocumentAndComplete();
    } catch (e) {
      if (!mounted) return;
      final errorStr = e.toString();

      if (errorStr.toLowerCase().contains('already exists')) {
        // Profile exists - check if ID document was uploaded
        if (_idDocumentUploaded) {
          setState(() => _error = 'Your worker application is already complete. You can switch to Worker mode from settings.');
        } else {
          setState(() {
            _error = 'A worker profile already exists. Uploading ID document to complete your application...';
            _currentStep = WorkerApplicationStep.idDocument;
          });
          // Profile exists, just need to upload ID document
          await _uploadIdDocumentAndComplete(isRetry: true);
        }
      } else if (errorStr.contains('Document upload') || errorStr.contains('Invalid document')) {
        setState(() => _error = 'ID document upload failed. Please verify your file and try again.');
        if (!mounted) return;
        setState(() => _currentStep = WorkerApplicationStep.idDocument);
      } else {
        setState(() => _error = errorStr);
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _uploadIdDocumentAndComplete({bool isRetry = false}) async {
    try {
      await WorkerAppApi.uploadIdDocument(
        docType: _selectedIdType,
        file: _idDocument!,
      );

      if (!mounted) return;

      // Check if document was successfully uploaded
      setState(() {
        _idDocumentUploaded = true;
        _error = null;
      });

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Application submitted! Your profile is under review. Please allow 24-48 hours for admin verification.'),
          backgroundColor: Colors.green,
        ),
      );
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      final errorStr = e.toString();

      if (errorStr.contains('Document upload failed') || errorStr.contains('Invalid document') || errorStr.contains('doc_type') || errorStr.contains('file')) {
        setState(() => _error = 'ID document upload failed. Please verify your file and try again.');
        if (!mounted) return;
        setState(() {
          _idDocumentUploaded = false;
          _idDocument = null;
          _currentStep = WorkerApplicationStep.idDocument;
        });
      } else {
        setState(() => _error = errorStr);
      }
    }
  }

  void _goBack() {
    switch (_currentStep) {
      case WorkerApplicationStep.photo:
        Navigator.of(context).pop();
        break;
      case WorkerApplicationStep.services:
        setState(() => _currentStep = WorkerApplicationStep.photo);
        break;
      case WorkerApplicationStep.zones:
        setState(() => _currentStep = WorkerApplicationStep.services);
        break;
      case WorkerApplicationStep.idDocument:
        setState(() => _currentStep = WorkerApplicationStep.zones);
        break;
      case WorkerApplicationStep.review:
        setState(() => _currentStep = WorkerApplicationStep.idDocument);
        break;
    }
  }

  void _nextStep() {
    switch (_currentStep) {
      case WorkerApplicationStep.photo:
        if (_profilePhoto == null && !_hasExistingPhoto) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Please take a profile photo first.')),
          );
          return;
        }
        setState(() => _currentStep = WorkerApplicationStep.services);
        break;
      case WorkerApplicationStep.services:
        if (_selectedServiceIds.isEmpty) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Please select at least one service.')),
          );
          return;
        }
        if (_selectedServiceIds.any((id) => (_buildServiceCapabilities()[id]?.isNotEmpty ?? false) == false)) {
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Choose or enter at least one task for every selected service.')));
          return;
        }
        setState(() => _currentStep = WorkerApplicationStep.zones);
        break;
      case WorkerApplicationStep.zones:
        if (_selectedZoneIds.isEmpty) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Please select at least one service zone.')),
          );
          return;
        }
        setState(() => _currentStep = WorkerApplicationStep.idDocument);
        break;
      case WorkerApplicationStep.idDocument:
        if (_idDocument == null) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Please upload an ID document (Aadhaar or other ID).')),
          );
          return;
        }
        setState(() => _currentStep = WorkerApplicationStep.review);
        break;
      case WorkerApplicationStep.review:
        break;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Become a Worker'),
        backgroundColor: AirwayColors.primary,
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? _buildErrorState()
              : _buildStepContent(),
    );
  }

  Widget _buildErrorState() => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.error_outline, size: 48, color: AirwayColors.error),
              const SizedBox(height: 16),
              Text(_error!, textAlign: TextAlign.center, style: const TextStyle(fontSize: 14)),
              const SizedBox(height: 16),
              OutlinedButton(onPressed: _submitApplication, child: const Text('Retry')),
            ],
          ),
        ),
      );

  Widget _buildStepContent() {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _buildStepIndicator(),
        const SizedBox(height: 24),
        _buildStepContentByStep(),
        const SizedBox(height: 16),
        _buildNavigationButtons(),
      ],
    );
  }

  Widget _buildStepIndicator() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4),
      child: Row(
        children: List.generate(WorkerApplicationStep.values.length, (index) {
          final isCompleted = index < _currentStep.index;
          final isActive = index == _currentStep.index;
          final color = isCompleted
              ? Colors.green
              : isActive
                  ? AirwayColors.primary
                  : AirwayColors.textSecondary.withAlpha(110);
          return Expanded(
            child: Padding(
              padding: EdgeInsets.only(
                right: index == WorkerApplicationStep.values.length - 1 ? 0 : 7,
              ),
              child: Container(
                height: 34,
                decoration: BoxDecoration(
                  color: color.withAlpha(isActive || isCompleted ? 24 : 12),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: color.withAlpha(90)),
                ),
                child: Icon(
                  isCompleted
                      ? Icons.check_rounded
                      : Icons.arrow_forward_rounded,
                  color: color,
                  size: 19,
                ),
              ),
            ),
          );
        }),
      ),
    );
  }

  Widget _buildStepContentByStep() {
    switch (_currentStep) {
      case WorkerApplicationStep.photo:
        return _buildPhotoSection();
      case WorkerApplicationStep.services:
        return _buildServicesSection();
      case WorkerApplicationStep.zones:
        return _buildZonesSection();
      case WorkerApplicationStep.idDocument:
        return _buildIdDocumentSection();
      case WorkerApplicationStep.review:
        return _buildReviewSection();
    }
  }

  Widget _buildPhotoSection() {
    final hasExistingPhoto = _hasExistingPhoto;
    final isTakingNewPhoto = _profilePhoto != null;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Card(
          elevation: 2,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          child: ListTile(
            contentPadding: const EdgeInsets.all(16),
            leading: CircleAvatar(
              radius: 28,
              backgroundColor: AirwayColors.primarySoft,
              child: isTakingNewPhoto
                  ? ClipOval(child: Image.file(_profilePhoto!, width: 48, height: 48, fit: BoxFit.cover))
                  : hasExistingPhoto
                      ? Icon(Icons.check_circle, size: 32, color: Colors.green[700])
                      : const Icon(Icons.person, size: 32, color: AirwayColors.primary),
            ),
            title: const Text('Profile Photo *', style: TextStyle(fontWeight: FontWeight.w800)),
            subtitle: Text(
              isTakingNewPhoto ? 'Photo ready for verification' : 'Required for worker verification',
              style: const TextStyle(color: AirwayColors.textSecondary),
            ),
            trailing: TextButton(onPressed: _pickPhoto, child: Text(isTakingNewPhoto ? 'Retake' : hasExistingPhoto ? 'Replace' : 'Take Photo')),
            onTap: _pickPhoto,
          ),
        ),
        const SizedBox(height: 20),
        Text('Personal & Professional Details', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: AirwayColors.text)),
        const SizedBox(height: 10),
        TextField(controller: _nameController, decoration: const InputDecoration(labelText: 'Full legal name *', border: OutlineInputBorder())),
        const SizedBox(height: 10),
        TextField(controller: _emailController, keyboardType: TextInputType.emailAddress, decoration: const InputDecoration(labelText: 'Email address', border: OutlineInputBorder())),
        const SizedBox(height: 10),
        DropdownButtonFormField<String>(
          initialValue: _selectedGender,
          decoration: const InputDecoration(labelText: 'Gender (for service matching)', border: OutlineInputBorder()),
          items: const [
            DropdownMenuItem(value: 'male', child: Text('Male')),
            DropdownMenuItem(value: 'female', child: Text('Female')),
            DropdownMenuItem(value: 'other', child: Text('Other')),
          ],
          onChanged: (value) { if (value != null) setState(() => _selectedGender = value); },
        ),
        const SizedBox(height: 10),
        TextField(controller: _addressController, maxLines: 2, decoration: const InputDecoration(labelText: 'Residential address *', border: OutlineInputBorder())),
        const SizedBox(height: 10),
        TextField(controller: _landmarkController, decoration: const InputDecoration(labelText: 'Nearby landmark', border: OutlineInputBorder())),
        const SizedBox(height: 10),
        TextField(controller: _upiController, decoration: const InputDecoration(labelText: 'UPI ID for payouts (optional)', border: OutlineInputBorder())),
        const SizedBox(height: 10),
        TextField(controller: _qualificationController, decoration: const InputDecoration(labelText: 'Qualification / training', border: OutlineInputBorder())),
        const SizedBox(height: 10),
        TextField(controller: _experienceController, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Experience (years)', border: OutlineInputBorder())),
        const SizedBox(height: 10),
        TextField(controller: _equipmentController, maxLines: 2, decoration: const InputDecoration(labelText: 'Tools, equipment or products you can bring', border: OutlineInputBorder())),
        const SizedBox(height: 10),
        TextField(controller: _bioController, maxLines: 3, decoration: const InputDecoration(labelText: 'About your work / skills', border: OutlineInputBorder())),
      ],
    );
  }

  Widget _buildServicesSection() {
    final grouped = <String, List<Service>>{};
    for (final service in _services) {
      grouped.putIfAbsent(service.categoryName, () => []).add(service);
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Services You Offer *',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: AirwayColors.text),
        ),
        const SizedBox(height: 8),
        const Text(
          'Choose every individual service you are trained and willing to provide. Customers will only see services that have an approved, eligible worker in their area.',
          style: TextStyle(color: AirwayColors.textSecondary),
        ),
        const SizedBox(height: 12),
        if (_services.isEmpty)
          const Text('No active services are available for worker registration.')
        else
          ...grouped.entries.map((entry) => Padding(
                padding: const EdgeInsets.only(bottom: 18),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(entry.key, style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: AirwayColors.primary)),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: entry.value.map((service) {
                        final selected = _selectedServiceIds.contains(service.id);
                        return FilterChip(
                          selected: selected,
                          label: Text(service.title),
                          onSelected: (_) => _toggleService(service.id),
                          selectedColor: AirwayColors.primary.withAlpha(30),
                          labelStyle: TextStyle(color: selected ? Colors.white : AirwayColors.text),
                        );
                      }).toList(),
                    ),
                  ],
                ),
              )),
        if (_selectedServiceIds.isNotEmpty) ...[
          const Divider(height: 28),
          Text("Specific tasks you can perform", style: TextStyle(fontSize: 17, fontWeight: FontWeight.w800, color: AirwayColors.text)),
          const SizedBox(height: 6),
          const Text("Choose tasks listed in your service packages where available. Add any other work you are trained to perform, separated by commas. Admin will verify these claims.", style: TextStyle(color: AirwayColors.textSecondary)),
          const SizedBox(height: 10),
          ..._services.where((service) => _selectedServiceIds.contains(service.id)).map((service) {
            final tasks = service.variants.expand((variant) => variant.includedTasks).map((task) => task.trim()).where((task) => task.isNotEmpty).toSet().toList()..sort();
            final controller = _capabilityControllers.putIfAbsent(service.id, () => TextEditingController());
            final selected = _selectedServiceCapabilities.putIfAbsent(service.id, () => <String>{});
            return Card(margin: const EdgeInsets.only(bottom: 10), child: Padding(padding: const EdgeInsets.all(12), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(service.title, style: const TextStyle(fontWeight: FontWeight.w800)),
              if (tasks.isNotEmpty) ...[
                const SizedBox(height: 8),
                Wrap(spacing: 6, runSpacing: 6, children: tasks.map((task) => FilterChip(label: Text(task), selected: selected.contains(task), onSelected: (value) => setState(() { if (value) { selected.add(task); } else { selected.remove(task); } }))).toList()),
              ],
              const SizedBox(height: 8),
              TextField(controller: controller, maxLines: 2, decoration: const InputDecoration(labelText: "Other tasks (comma separated)", hintText: "e.g. root touch-up, hair spa", border: OutlineInputBorder())),
              if (tasks.isEmpty) const Padding(padding: EdgeInsets.only(top: 6), child: Text("No package task checklist is configured yet. Enter the exact tasks you can perform.", style: TextStyle(fontSize: 12, color: AirwayColors.textSecondary))),
            ])));
          }),
        ],
      ],
    );
  }


  Widget _buildZonesSection() => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Service Zones *',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: AirwayColors.text),
          ),
          const SizedBox(height: 8),
          const Text(
            'Areas where you are available to work',
            style: TextStyle(color: AirwayColors.textSecondary),
          ),
          const SizedBox(height: 12),
          _loading
              ? const Center(child: CircularProgressIndicator())
              : _error != null
                  ? Text('Failed to load zones: $_error', style: const TextStyle(color: Colors.red))
                  : _zones.isEmpty
                      ? const Text('No zones available')
                      : Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: _zones.map<Widget>((zone) {
                            final zoneMap = zone as Map<String, dynamic>;
                            final isSelected = _selectedZoneIds.contains(zoneMap['id']);
                            return ChoiceChip(
                              selected: isSelected,
                              label: Column(
                                mainAxisSize: MainAxisSize.min,
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(zoneMap['name'] as String, style: TextStyle(
                                    color: isSelected ? Colors.white : AirwayColors.text,
                                    fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                                  )),
                                  if (zoneMap['city_name'] != null)
                                    Text(zoneMap['city_name'] as String,
                                      style: TextStyle(
                                        fontSize: 10,
                                        color: isSelected ? Colors.white70 : AirwayColors.textSecondary,
                                      ),
                                    ),
                                ],
                              ),
                              onSelected: (_) => _toggleZone(zoneMap['id'] as int),
                              selectedColor: AirwayColors.primary,
                              labelStyle: const TextStyle(),
                            );
                          }).toList(),
                        ),
          const SizedBox(height: 24),
          _buildScheduleSection(),
        ],
      );

  String _timeText(String value) {
    final parts = value.split(':');
    final hour = int.parse(parts[0]);
    final minute = int.parse(parts[1]);
    final time = TimeOfDay(hour: hour, minute: minute);
    return time.format(context);
  }

  Future<void> _pickScheduleTime(int weekday, String key) async {
    final current = _weeklySchedule[weekday]!;
    final parts = current[key]!.split(':');
    final initial = TimeOfDay(hour: int.parse(parts[0]), minute: int.parse(parts[1]));
    final picked = await showTimePicker(context: context, initialTime: initial);
    if (picked == null) return;
    final value = '${picked.hour.toString().padLeft(2, '0')}:${picked.minute.toString().padLeft(2, '0')}';
    setState(() => current[key] = value);
  }

  Widget _buildScheduleSection() {
    const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Weekly Working Hours *', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: AirwayColors.text)),
        const SizedBox(height: 6),
        const Text('Choose the days and exact hours when you can accept jobs.', style: TextStyle(color: AirwayColors.textSecondary)),
        const SizedBox(height: 8),
        ...List.generate(7, (day) {
          final selected = _weeklySchedule.containsKey(day);
          return Card(
            child: Column(
              children: [
                CheckboxListTile(
                  value: selected,
                  title: Text(days[day]),
                  onChanged: (value) => setState(() {
                    if (value == true) {
                      _weeklySchedule[day] = {'start': '09:00', 'end': '18:00'};
                    } else {
                      _weeklySchedule.remove(day);
                    }
                  }),
                ),
                if (selected)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
                    child: Row(
                      children: [
                        Expanded(child: OutlinedButton(onPressed: () => _pickScheduleTime(day, 'start'), child: Text('From ${_timeText(_weeklySchedule[day]!['start']!)}'))),
                        const SizedBox(width: 8),
                        Expanded(child: OutlinedButton(onPressed: () => _pickScheduleTime(day, 'end'), child: Text('To ${_timeText(_weeklySchedule[day]!['end']!)}'))),
                      ],
                    ),
                  ),
              ],
            ),
          );
        }),
      ],
    );
  }

  Widget _buildIdDocumentSection() {
    final hasExistingIdDoc = _idDocumentUploaded;
    final isReplacingDoc = _idDocument != null;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'ID Document *',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: AirwayColors.text),
        ),
        const SizedBox(height: 8),
        const Text(
          'Please upload a valid government ID for verification. Aadhaar or any government-issued photo ID is accepted.',
          style: TextStyle(color: AirwayColors.textSecondary),
        ),
        const SizedBox(height: 16),
        DropdownButtonFormField<String>(
          initialValue: _selectedIdType,
          items: const [
            DropdownMenuItem(value: 'aadhaar', child: Text('Aadhaar (Recommended)')),
            DropdownMenuItem(value: 'id', child: Text('Other ID')),
          ],
          onChanged: (value) {
            if (value != null) {
              setState(() => _selectedIdType = value);
            }
          },
          decoration: const InputDecoration(
            labelText: 'ID Type',
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 16),
        Row(
          children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: () {
                  // Show dialog to explain behavior for existing PENDING docs
                  if (hasExistingIdDoc && !isReplacingDoc) {
                    _showIdDocDialog();
                  } else {
                    _pickIdDocument();
                  }
                },
                icon: const Icon(Icons.upload_file),
                label: Text(isReplacingDoc
                    ? 'Change Document'
                    : hasExistingIdDoc
                        ? 'View/ID Document Uploaded'
                        : 'Upload ID Document'),
              ),
            ),
          ],
        ),
        if (hasExistingIdDoc && !isReplacingDoc) ...[
          const SizedBox(height: 16),
          Card(
            elevation: 2,
            color: Colors.green.withAlpha(20),
            child: ListTile(
              leading: const Icon(Icons.check_circle, color: Colors.green),
              title: const Text('Document Submitted', style: TextStyle(color: Colors.green)),
              subtitle: Text('Type: ${_selectedIdType.toUpperCase()}'),
              trailing: const Icon(Icons.pending_actions, color: Colors.orange),
            ),
          ),
        ],
        if (isReplacingDoc) ...[
          const SizedBox(height: 16),
          Card(
            elevation: 2,
            child: ListTile(
              leading: const Icon(Icons.description, color: AirwayColors.primary),
              title: Text(
                _idDocument!.path.split('/').last,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              subtitle: Text('Type: ${_selectedIdType.toUpperCase()}'),
            ),
          ),
        ],
        const SizedBox(height: 24),
        const Text(
          'Note: Your application will be reviewed by our team. You will receive a notification once approved.',
          style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12),
        ),
      ],
    );
  }

  void _showIdDocDialog() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('ID Document Already Uploaded'),
        content: const Text(
          'Your ID document has already been submitted and is pending review. '
          'You can replace it with a new document if needed. Your existing document will be updated.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Keep Document'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              _pickIdDocument();
            },
            child: const Text('Upload New Document'),
          ),
        ],
      ),
    );
  }

  Widget _buildReviewSection() {
    final hasPhoto = _profilePhoto != null || _hasExistingPhoto;
    final hasIdDoc = _idDocument != null || _idDocumentUploaded;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Review Your Application',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: AirwayColors.text),
        ),
        const SizedBox(height: 16),
        _buildReviewItem('Profile Photo', hasPhoto),
        const Divider(),
        _buildReviewItem('Services', _selectedServiceIds.isNotEmpty, '${_selectedServiceIds.length} selected'),
        const Divider(),
        _buildReviewItem('Service Zones', _selectedZoneIds.isNotEmpty, '${_selectedZoneIds.length} selected'),
        const Divider(),
        _buildReviewItem('ID Document', hasIdDoc, hasIdDoc ? _selectedIdType.toUpperCase() : null),
        const Divider(),
        _buildReviewItem('Residential address', _addressController.text.trim().isNotEmpty),
        const Divider(),
        _buildReviewItem('Weekly working hours', _weeklySchedule.isNotEmpty, _weeklySchedule.length.toString() + ' day(s) selected'),
        const Divider(),
        _buildReviewItem('Qualification', _qualificationController.text.trim().isNotEmpty, _qualificationController.text.trim().isNotEmpty ? 'Added' : 'Optional'),
        const Divider(),
        _buildReviewItem('Experience', _experienceController.text.trim().isNotEmpty, _experienceController.text.trim().isEmpty ? 'Not provided' : _experienceController.text.trim() + ' years'),
        const Divider(),
        _buildReviewItem('Equipment / products', _equipmentController.text.trim().isNotEmpty, _equipmentController.text.trim().isNotEmpty ? 'Added' : 'Optional'),
        const Divider(),
        _buildReviewItem('Bio', _bioController.text.trim().isNotEmpty, _bioController.text.trim().isNotEmpty ? 'Added' : 'Optional'),
        const SizedBox(height: 24),
        const Card(
          color: Colors.amber,
          child: ListTile(
            leading: Icon(Icons.info_outline),
            title: Text('Important: Your application is subject to admin verification.'),
            subtitle: Text('You will be notified via in-app notification once approved.'),
          ),
        ),
      ],
    );
  }

  Widget _buildReviewItem(String label, bool hasItem, [String? detail]) {
    return ListTile(
      leading: Icon(
        hasItem ? Icons.check_circle : Icons.radio_button_unchecked,
        color: hasItem ? Colors.green : AirwayColors.textSecondary,
      ),
      title: Text(label),
      subtitle: detail != null ? Text(detail) : null,
      trailing: hasItem ? const Icon(Icons.check, color: Colors.green) : null,
    );
  }

  Widget _buildNavigationButtons() {
    final isFirstStep = _currentStep == WorkerApplicationStep.photo;
    final isLastStep = _currentStep == WorkerApplicationStep.review;

    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        if (!isFirstStep && !isLastStep)
          TextButton(onPressed: _goBack, child: const Text('Back'))
        else
          const SizedBox(width: 80),
        if (!isFirstStep && !isLastStep) ...[
          Expanded(
            child: ElevatedButton(
              onPressed: _nextStep,
              style: ElevatedButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 16),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
              child: const Text('Next', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
            ),
          ),
        ] else if (isLastStep) ...[
          Expanded(
            child: ElevatedButton(
              onPressed: _submitApplication,
              style: ElevatedButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 16),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
              child: const Text('Submit Application', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
            ),
          ),
        ] else ...[
          Expanded(
            child: ElevatedButton(
              onPressed: (_profilePhoto != null || _hasExistingPhoto) ? _nextStep : null,
              style: ElevatedButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 16),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
              child: const Text('Next', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
            ),
          ),
        ],
      ],
    );
  }
}