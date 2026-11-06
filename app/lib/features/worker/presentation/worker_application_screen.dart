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
  final List<int> _selectedZoneIds = [];
  int? _experienceYears;
  final TextEditingController _experienceController = TextEditingController();
  String? _bio;
  final TextEditingController _bioController = TextEditingController();

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
    super.dispose();
  }

  Future<void> _loadExistingApplication() async {
    try {
      final statusData = await WorkerAppApi.fetchWorkerApplicationStatus();
      if (statusData == null) return;

      final workerProfile = statusData['worker_profile'];
      if (workerProfile == null) return;

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
        _hasExistingPhoto = workerProfile['photo_url'] != null;

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
    if (_profilePhoto == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Profile photo is required. Please take a photo first.')),
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
        zoneIds: _selectedZoneIds,
        experienceYears: int.tryParse(_experienceController.text),
        bio: _bioController.text.isEmpty ? null : _bioController.text,
        profilePhoto: _profilePhoto,
      );

      if (!mounted) return;
      setState(() { _idDocumentUploaded = false; });

      // Application created successfully, now upload ID document
      await _uploadIdDocumentAndComplete();
    } catch (e) {
      if (!mounted) return;
      final errorStr = e.toString();

      if (errorStr.contains('Worker profile already exists')) {
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
        if (_profilePhoto == null) {
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

    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: ListTile(
        contentPadding: const EdgeInsets.all(16),
        leading: CircleAvatar(
          radius: 28,
          backgroundColor: AirwayColors.primarySoft,
          child: isTakingNewPhoto
              ? ClipOval(
                  child: Image.file(
                    _profilePhoto!,
                    width: 48,
                    height: 48,
                    fit: BoxFit.cover,
                  ),
                )
              : hasExistingPhoto
                  ? Icon(Icons.check_circle, size: 32, color: Colors.green[700])
                  : const Icon(Icons.person, size: 32, color: AirwayColors.primary),
        ),
        title: const Text('Profile Photo *', style: TextStyle(fontWeight: FontWeight.w800)),
        subtitle: Text(
          isTakingNewPhoto
              ? 'New photo taken - will be submitted for verification'
              : hasExistingPhoto
                  ? 'Existing verified photo - tap to change'
                  : 'Required for verification - take a photo with your device camera',
          style: const TextStyle(color: AirwayColors.textSecondary),
        ),
        trailing: TextButton(
          onPressed: _hasExistingPhoto && _profilePhoto == null ? null : _pickPhoto,
          child: Text(isTakingNewPhoto
              ? 'Retake'
              : hasExistingPhoto
                  ? 'Keep Photo'
                  : 'Take Photo'),
        ),
        onTap: _pickPhoto,
      ),
    );
  }

  Widget _buildServicesSection() => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Services You Offer *',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: AirwayColors.text),
          ),
          const SizedBox(height: 8),
          const Text(
            'Select all services you can perform',
            style: TextStyle(color: AirwayColors.textSecondary),
          ),
          const SizedBox(height: 12),
          _services.isEmpty
              ? const Text('Loading services...')
              : Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: _services.map((service) {
                    final isSelected = _selectedServiceIds.contains(service.id);
                    return FilterChip(
                      selected: isSelected,
                      label: Text(service.title),
                      onSelected: (_) => _toggleService(service.id),
                      selectedColor: AirwayColors.primary.withAlpha(30),
                      labelStyle: TextStyle(
                        color: isSelected ? Colors.white : AirwayColors.text,
                      ),
                    );
                  }).toList(),
                ),
        ],
      );

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
        ],
      );

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
        _buildReviewItem('Experience', _experienceYears != null && _experienceYears! > 0, '$_experienceYears years'),
        const Divider(),
        _buildReviewItem('Bio', _bio?.isNotEmpty == true, _bio?.isNotEmpty == true ? 'Added' : 'Not added'),
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
              onPressed: _profilePhoto != null ? _nextStep : null,
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