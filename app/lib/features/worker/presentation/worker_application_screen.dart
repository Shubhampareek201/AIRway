import 'dart:io';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:airway/core/localization/airway_text.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/worker/data/worker_app_api.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';
import 'package:image_picker/image_picker.dart';
import 'package:geolocator/geolocator.dart';
import 'package:airway/features/location/data/location_api.dart';
import 'package:airway/features/worker/presentation/widgets/worker_service_picker.dart';

enum WorkerApplicationStep { photo, services, zones, schedule, idDocument, review }

class WorkerApplicationScreen extends StatefulWidget {
  const WorkerApplicationScreen({super.key});

  @override
  State<WorkerApplicationScreen> createState() => _WorkerApplicationScreenState();
}

class _WorkerApplicationScreenState extends State<WorkerApplicationScreen> {
  WorkerApplicationStep _currentStep = WorkerApplicationStep.photo;

  List<Service> _services = [];
  final TextEditingController _serviceSearchController = TextEditingController();
  List<dynamic> _zones = [];
  final List<int> _selectedServiceIds = [];
  final Map<int, Set<String>> _selectedServiceCapabilities = {};
  final Map<String, String> _fieldErrors = {};
  final _photoKey = GlobalKey();
  final _nameKey = GlobalKey();
  final _emailKey = GlobalKey();
  final _genderKey = GlobalKey();
  final _addressKey = GlobalKey();
  final _servicesKey = GlobalKey();
  final _zonesKey = GlobalKey();
  final _scheduleKey = GlobalKey();
  final _idDocumentKey = GlobalKey();
  final List<int> _selectedZoneIds = [];
  final TextEditingController _bioController = TextEditingController();
  final TextEditingController _nameController = TextEditingController();
  final TextEditingController _emailController = TextEditingController();
  final TextEditingController _qualificationController = TextEditingController();
  final TextEditingController _equipmentController = TextEditingController();
  final TextEditingController _addressController = TextEditingController();
  final TextEditingController _landmarkController = TextEditingController();
  final TextEditingController _upiController = TextEditingController();
  String? _selectedGender;
  final Map<int, Map<String, String>> _weeklySchedule = {};

  File? _profilePhoto;
  File? _idDocument;
  String _selectedIdType = 'aadhaar';
  double? _latitude;
  double? _longitude;

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
  }

  @override
  void dispose() {
    _bioController.dispose();
    _nameController.dispose();
    _emailController.dispose();
    _qualificationController.dispose();
    _equipmentController.dispose();
    _addressController.dispose();
    _landmarkController.dispose();
    _upiController.dispose();
    _serviceSearchController.dispose();
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
        _existingBio = workerProfile['bio'];
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
      setState(() => _error = AirwayText.tr('Failed to load services/zones: $e', 'सेवाएँ / क्षेत्र लोड नहीं हो सके: $e'));
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
        setState(() {
          _profilePhoto = File(picked.path);
          _fieldErrors.remove('photo');
        });
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Failed to pick photo: $e', 'फ़ोटो नहीं चुनी जा सकी: $e'))),
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
        SnackBar(content: Text(AirwayText.tr('Failed to pick document: $e', 'दस्तावेज़ नहीं चुना जा सका: $e'))),
      );
    }
  }

  void _clearValidationError(String field) {
    if (!_fieldErrors.containsKey(field) || !mounted) return;
    setState(() => _fieldErrors.remove(field));
  }

  Future<void> _showStepErrors(Map<String, String> errors) async {
    if (!mounted) return;
    setState(() {
      _fieldErrors
        ..clear()
        ..addAll(errors);
    });
    final firstField = errors.keys.first;
    await Future<void>.delayed(const Duration(milliseconds: 60));
    if (!mounted) return;
    final target = <String, GlobalKey>{
      'photo': _photoKey,
      'name': _nameKey,
      'email': _emailKey,
      'gender': _genderKey,
      'address': _addressKey,
      'services': _servicesKey,
      'zones': _zonesKey,
      'schedule': _scheduleKey,
      'id_document': _idDocumentKey,
    }[firstField]?.currentContext;
    if (target != null) {
      await Scrollable.ensureVisible(
        target,
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeInOut,
        alignment: 0.18,
      );
    }
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(errors.values.first)),
      );
    }
  }

  Map<int, List<String>> _buildServiceCapabilities() {
    return {
      for (final serviceId in _selectedServiceIds)
        serviceId: (_selectedServiceCapabilities[serviceId] ?? <String>{}).toList(),
    };
  }

  void _toggleZone(int zoneId) {
    setState(() {
      if (_selectedZoneIds.contains(zoneId)) {
        _selectedZoneIds.remove(zoneId);
      } else {
        _selectedZoneIds.add(zoneId);
      }
      _fieldErrors.remove('zones');
    });
  }

  double _distanceMeters(double lat1, double lon1, double lat2, double lon2) {
    const earthRadius = 6371000.0;
    final dLat = (lat2 - lat1) * math.pi / 180;
    final dLon = (lon2 - lon1) * math.pi / 180;
    final a = math.pow(math.sin(dLat / 2), 2) +
        math.cos(lat1 * math.pi / 180) * math.cos(lat2 * math.pi / 180) *
        math.pow(math.sin(dLon / 2), 2);
    return earthRadius * 2 * math.asin(math.sqrt(a));
  }

  Future<void> _fetchCurrentLocation() async {
    if (_loading) return;
    setState(() { _loading = true; _error = null; });
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        throw Exception('Please turn on Location/GPS on your phone, then try again.');
      }

      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.deniedForever) {
        throw Exception('Location permission is blocked. Allow it in phone Settings, or enter your address manually.');
      }
      if (permission == LocationPermission.denied) {
        throw Exception('Location permission was not granted. You can enter your address manually.');
      }

      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(accuracy: LocationAccuracy.high),
      ).timeout(const Duration(seconds: 25));

      // Keep GPS even when the reverse-geocoding provider is temporarily unavailable.
      String formatted = '';
      try {
        final address = await LocationApi.reverse(position.latitude, position.longitude);
        formatted = (address['formatted'] ?? '').toString().trim();
      } catch (_) {
        // The worker can enter the address manually.
      }

      final matches = <Map<String, dynamic>>[];
      for (final raw in _zones) {
        if (raw is! Map) continue;
        final zone = Map<String, dynamic>.from(raw);
        final lat = double.tryParse(zone['latitude']?.toString() ?? '');
        final lon = double.tryParse(zone['longitude']?.toString() ?? '');
        final radius = int.tryParse(zone['coverage_radius_meters']?.toString() ?? '') ?? 0;
        if (lat == null || lon == null || radius <= 0) continue;
        final distance = _distanceMeters(position.latitude, position.longitude, lat, lon);
        if (distance <= radius) {
          zone['_distance'] = distance;
          matches.add(zone);
        }
      }
      matches.sort((a, b) =>
          (a['_distance'] as double).compareTo(b['_distance'] as double));

      if (!mounted) return;
      setState(() {
        _latitude = position.latitude;
        _longitude = position.longitude;
        if (formatted.isNotEmpty) _addressController.text = formatted;
        // GPS only suggests a nearby work area; it never restricts the worker.
        if (matches.isNotEmpty) {
          final nearestId = matches.first['id'];
          if (nearestId is int && !_selectedZoneIds.contains(nearestId)) {
            _selectedZoneIds.add(nearestId);
          }
        }
      });

      final message = formatted.isEmpty
          ? 'GPS captured. Enter your residential address manually and choose your working areas below.'
          : matches.isEmpty
              ? 'Address detected. Choose the AIRway areas where you are willing to work.'
              : 'Address detected. Nearby area suggested; you can select multiple working areas.';
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
    } catch (e) {
      if (mounted) {
        final message = e.toString().replaceFirst('Exception: ', '');
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _submitApplication() async {
    if (!mounted) return;
    if (_profilePhoto == null && !_hasExistingPhoto) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Profile photo is required. Please take a photo first.', 'प्रोफ़ाइल फ़ोटो ज़रूरी है। पहले फ़ोटो लें।'))),
      );
      return;
    }
    if (_nameController.text.trim().isEmpty || _addressController.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Please enter your full name and residential address.', 'अपना पूरा नाम और आवासीय पता दर्ज करें।'))),
      );
      return;
    }
    if (_weeklySchedule.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Please select at least one working day and its hours.', 'कम से कम एक कार्य दिवस और उसके घंटे चुनें।'))),
      );
      return;
    }

    if (_selectedServiceIds.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Please select at least one service.', 'कम से कम एक सेवा चुनें।'))),
      );
      return;
    }

    if (_selectedZoneIds.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Please select at least one service zone.', 'कम से कम एक सेवा क्षेत्र चुनें।'))),
      );
      return;
    }

    if (_idDocument == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Please upload an ID document.', 'कृपया पहचान दस्तावेज़ अपलोड करें।'))),
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
        experienceYears: null,
        bio: _bioController.text.isEmpty ? null : _bioController.text,
        name: _nameController.text.trim(),
        email: _emailController.text.trim(),
        gender: _selectedGender ?? '',
        qualification: _qualificationController.text,
        equipmentDetails: _equipmentController.text,
        residentialAddress: _addressController.text.trim(),
        latitude: _latitude,
        longitude: _longitude,
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
          setState(() => _error = AirwayText.tr('Your worker application is already complete. You can switch to Worker mode from settings.', 'आपका वर्कर आवेदन पहले से पूरा है। सेटिंग्स से वर्कर मोड पर जा सकते हैं।'));
        } else {
          setState(() {
            _error = AirwayText.tr('A worker profile already exists. Uploading ID document to complete your application...', 'वर्कर प्रोफ़ाइल पहले से मौजूद है। आवेदन पूरा करने के लिए पहचान दस्तावेज़ अपलोड हो रहा है...');
            _currentStep = WorkerApplicationStep.idDocument;
          });
          // Profile exists, just need to upload ID document
          await _uploadIdDocumentAndComplete(isRetry: true);
        }
      } else if (errorStr.contains('Document upload') || errorStr.contains('Invalid document')) {
        setState(() => _error = AirwayText.tr('ID document upload failed. Please verify your file and try again.', 'पहचान दस्तावेज़ अपलोड नहीं हुआ। फ़ाइल जाँचकर फिर कोशिश करें।'));
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
        SnackBar(
          content: Text(AirwayText.tr('Application submitted! Your profile is under review. Please allow 24-48 hours for admin verification.', 'आवेदन भेज दिया गया है! आपकी प्रोफ़ाइल समीक्षा में है। एडमिन वेरिफ़िकेशन के लिए 24-48 घंटे दें।')),
          backgroundColor: Colors.green,
        ),
      );
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      final errorStr = e.toString();

      if (errorStr.contains('Document upload failed') || errorStr.contains('Invalid document') || errorStr.contains('doc_type') || errorStr.contains('file')) {
        setState(() => _error = AirwayText.tr('ID document upload failed. Please verify your file and try again.', 'पहचान दस्तावेज़ अपलोड नहीं हुआ। फ़ाइल जाँचकर फिर कोशिश करें।'));
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
      case WorkerApplicationStep.schedule:
        setState(() => _currentStep = WorkerApplicationStep.zones);
        break;
      case WorkerApplicationStep.idDocument:
        setState(() => _currentStep = WorkerApplicationStep.schedule);
        break;
      case WorkerApplicationStep.review:
        setState(() => _currentStep = WorkerApplicationStep.idDocument);
        break;
    }
  }

  void _nextStep() {
    _fieldErrors.clear();
    switch (_currentStep) {
      case WorkerApplicationStep.photo:
        final errors = <String, String>{};
        if (_profilePhoto == null && !_hasExistingPhoto) {
          errors['photo'] = 'Profile photo is required. Take a clear photo to continue.';
        }
        if (_nameController.text.trim().isEmpty) {
          errors['name'] = 'Enter your full legal name.';
        }
        final email = _emailController.text.trim();
        if (email.isEmpty || !RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(email)) {
          errors['email'] = 'Enter a valid email address.';
        }
        if (_selectedGender == null) {
          errors['gender'] = 'Select your gender.';
        }
        if (_addressController.text.trim().isEmpty) {
          errors['address'] = 'Enter your residential address or use GPS.';
        }
        if (errors.isNotEmpty) {
          _showStepErrors(errors);
          return;
        }
        setState(() => _currentStep = WorkerApplicationStep.services);
        break;
      case WorkerApplicationStep.services:
        if (_selectedServiceIds.isEmpty) {
          _showStepErrors({'services': 'Select at least one service you can provide.'});
          return;
        }
        setState(() => _currentStep = WorkerApplicationStep.zones);
        break;
      case WorkerApplicationStep.zones:
        if (_selectedZoneIds.isEmpty) {
          _showStepErrors({'zones': 'Select at least one area where you are willing to work.'});
          return;
        }
        setState(() => _currentStep = WorkerApplicationStep.schedule);
        break;
      case WorkerApplicationStep.schedule:
        final invalidDays = _weeklySchedule.entries.any((entry) {
          final start = entry.value['start'];
          final end = entry.value['end'];
          if (start == null || end == null) return true;
          final startParts = start.split(':').map(int.tryParse).toList();
          final endParts = end.split(':').map(int.tryParse).toList();
          if (startParts.length != 2 || endParts.length != 2 ||
              startParts.any((part) => part == null) || endParts.any((part) => part == null)) return true;
          return endParts[0]! * 60 + endParts[1]! <= startParts[0]! * 60 + startParts[1]!;
        });
        if (_weeklySchedule.isEmpty || invalidDays) {
          _showStepErrors({
            'schedule': _weeklySchedule.isEmpty
                ? 'Select at least one working day.'
                : 'For every selected day, the end time must be later than the start time.',
          });
          return;
        }
        setState(() => _currentStep = WorkerApplicationStep.idDocument);
        break;
      case WorkerApplicationStep.idDocument:
        if (_idDocument == null && !_idDocumentUploaded) {
          _showStepErrors({'id_document': 'Upload a clear government ID document to continue.'});
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
        leading: IconButton(
          tooltip: AirwayText.tr('Go back', 'वापस जाएँ'),
          icon: const Icon(Icons.arrow_back),
          onPressed: _goBack,
        ),
        title: Text(AirwayText.tr('Become a Worker', 'वर्कर बनें')),
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
              OutlinedButton(onPressed: _loadServicesAndZones, child: Text(AirwayText.tr('Retry loading services and areas', 'सेवाएँ और क्षेत्र फिर से लोड करें'))),
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
      case WorkerApplicationStep.schedule:
        return _buildScheduleSection();
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
          key: _photoKey,
          elevation: 2,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
            side: BorderSide(
              color: _fieldErrors.containsKey('photo') ? Colors.red : Colors.transparent,
              width: 1.5,
            ),
          ),
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
            title: Text(AirwayText.tr('Profile Photo *', 'प्रोफ़ाइल फ़ोटो *'), style: TextStyle(fontWeight: FontWeight.w800)),
            subtitle: Text(
              _fieldErrors['photo'] ??
                  (isTakingNewPhoto ? 'Photo ready for verification' : 'Required for worker verification'),
              style: TextStyle(
                color: _fieldErrors.containsKey('photo') ? Colors.red : AirwayColors.textSecondary,
              ),
            ),
            trailing: TextButton(onPressed: _pickPhoto, child: Text(isTakingNewPhoto ? 'Retake' : hasExistingPhoto ? 'Replace' : 'Take Photo')),
            onTap: _pickPhoto,
          ),
        ),
        const SizedBox(height: 20),
        Text(AirwayText.tr('Personal & Professional Details', 'व्यक्तिगत और पेशेवर जानकारी'), style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: AirwayColors.text)),
        const SizedBox(height: 10),
        TextField(
          key: _nameKey,
          controller: _nameController,
          onChanged: (_) => _clearValidationError('name'),
          decoration: InputDecoration(
            labelText: AirwayText.tr('Full legal name *', 'पूरा कानूनी नाम *'),
            border: const OutlineInputBorder(),
            errorText: _fieldErrors['name'],
          ),
        ),
        const SizedBox(height: 10),
        TextField(
          key: _emailKey,
          controller: _emailController,
          keyboardType: TextInputType.emailAddress,
          onChanged: (_) => _clearValidationError('email'),
          decoration: InputDecoration(
            labelText: AirwayText.tr('Email address *', 'ईमेल पता *'),
            border: const OutlineInputBorder(),
            errorText: _fieldErrors['email'],
          ),
        ),
        const SizedBox(height: 10),
        DropdownButtonFormField<String>(
          key: _genderKey,
          initialValue: _selectedGender,
          decoration: InputDecoration(
            labelText: AirwayText.tr('Gender * (used for service matching)', 'लिंग * (सेवा मिलान के लिए)'),
            border: const OutlineInputBorder(),
            errorText: _fieldErrors['gender'],
          ),
          items: [
            DropdownMenuItem(value: 'male', child: Text(AirwayText.tr('Male', 'पुरुष'))),
            DropdownMenuItem(value: 'female', child: Text(AirwayText.tr('Female', 'महिला'))),
            DropdownMenuItem(value: 'other', child: Text(AirwayText.tr('Other', 'अन्य'))),
          ],
          onChanged: (value) {
            if (value != null) {
              setState(() {
                _selectedGender = value;
                _fieldErrors.remove('gender');
              });
            }
          },
        ),
        const SizedBox(height: 10),
        TextField(
          key: _addressKey,
          controller: _addressController,
          maxLines: 2,
          onChanged: (_) => _clearValidationError('address'),
          decoration: InputDecoration(
            labelText: AirwayText.tr('Residential address *', 'आवासीय पता *'),
            hintText: AirwayText.tr('Use GPS or type your complete address', 'GPS इस्तेमाल करें या पूरा पता लिखें'),
            border: const OutlineInputBorder(),
            errorText: _fieldErrors['address'],
          ),
        ),
        const SizedBox(height: 6),
        SizedBox(width: double.infinity, child: OutlinedButton.icon(
          onPressed: _loading ? null : _fetchCurrentLocation,
          icon: const Icon(Icons.my_location),
          label: Text(AirwayText.tr('Use my current location', 'मेरी वर्तमान लोकेशन इस्तेमाल करें')),
        )),
        if (_latitude != null && _longitude != null)
          Padding(padding: const EdgeInsets.only(top: 4), child: Text(AirwayText.tr('GPS location attached. Service area selected automatically.', 'GPS लोकेशन जुड़ गई। सेवा क्षेत्र अपने आप चुना गया।'), style: TextStyle(color: Colors.green, fontSize: 12))),
        const SizedBox(height: 10),
        TextField(controller: _landmarkController, decoration: InputDecoration(labelText: AirwayText.tr('Nearby landmark', 'नज़दीकी लैंडमार्क'), border: OutlineInputBorder())),
        const SizedBox(height: 10),
        TextField(controller: _upiController, decoration: InputDecoration(labelText: AirwayText.tr('UPI ID for payouts (optional)', 'भुगतान के लिए UPI ID (वैकल्पिक)'), border: OutlineInputBorder())),
        const SizedBox(height: 10),
        TextField(controller: _qualificationController, decoration: InputDecoration(labelText: AirwayText.tr('Qualification / training', 'योग्यता / प्रशिक्षण'), border: OutlineInputBorder())),
        const SizedBox(height: 10),

        TextField(controller: _equipmentController, maxLines: 2, decoration: InputDecoration(labelText: AirwayText.tr('Tools, equipment or products you can bring', 'आप कौन-से औज़ार, उपकरण या उत्पाद ला सकते हैं'), border: OutlineInputBorder())),
        const SizedBox(height: 10),
        TextField(controller: _bioController, maxLines: 3, decoration: InputDecoration(labelText: AirwayText.tr('About your work / skills', 'आपके काम / कौशल के बारे में'), border: OutlineInputBorder())),
      ],
    );
  }

  Widget _buildServicesSection() {
    if (_services.isEmpty) {
      return Text(AirwayText.tr('No active launch services are available for worker registration. Please contact AIRway support.', 'वर्कर रजिस्ट्रेशन के लिए अभी कोई सक्रिय सेवा उपलब्ध नहीं है। AIRway सपोर्ट से संपर्क करें।'));
    }
    return WorkerServicePicker(
      services: _services,
      selectedIds: _selectedServiceIds.toSet(),
      capabilities: _selectedServiceCapabilities,
      errorText: _fieldErrors['services'],
      onServiceAdded: (id) => setState(() {
        if (!_selectedServiceIds.contains(id)) _selectedServiceIds.add(id);
        _selectedServiceCapabilities.putIfAbsent(id, () => <String>{});
        _fieldErrors.remove('services');
      }),
      onServiceRemoved: (id) => setState(() {
        _selectedServiceIds.remove(id);
        _selectedServiceCapabilities.remove(id);
      }),
      onCapabilityChanged: (id, task, selected) => setState(() {
        final values = _selectedServiceCapabilities.putIfAbsent(id, () => <String>{});
        if (selected) { values.add(task); } else { values.remove(task); }
      }),
    );
  }

  Widget _buildZonesSection() => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Where are you willing to work? *',
            key: _zonesKey,
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: _fieldErrors.containsKey('zones') ? Colors.red : AirwayColors.text),
          ),
          if (_fieldErrors['zones'] != null)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(_fieldErrors['zones']!, style: const TextStyle(color: Colors.red, fontSize: 12)),
            ),
          const SizedBox(height: 8),
          Text(
            AirwayText.tr('Your home address and working areas are different. Choose every active AIRway area you can travel to. GPS only suggests a nearby area; it never limits your selection.', 'आपका घर का पता और कार्य क्षेत्र अलग हैं। वे सभी सक्रिय AIRway क्षेत्र चुनें जहाँ आप काम के लिए जा सकते हैं। GPS केवल नज़दीकी क्षेत्र सुझाता है; यह आपकी पसंद सीमित नहीं करता।'),
            style: const TextStyle(color: AirwayColors.textSecondary),
          ),
          const SizedBox(height: 12),
          if (_zones.isEmpty)
            Text(AirwayText.tr('No active service areas are configured yet. Please contact AIRway support.', 'अभी कोई सक्रिय सेवा क्षेत्र कॉन्फ़िगर नहीं है। AIRway सपोर्ट से संपर्क करें।'))
          else
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: _zones.map<Widget>((rawZone) {
                final zoneMap = Map<String, dynamic>.from(rawZone as Map);
                final zoneId = int.tryParse(zoneMap['id'].toString());
                if (zoneId == null) return const SizedBox.shrink();
                final isSelected = _selectedZoneIds.contains(zoneId);
                final cityName = zoneMap['city_name']?.toString();
                return FilterChip(
                  selected: isSelected,
                  label: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(zoneMap['name']?.toString() ?? 'Service area',
                          style: const TextStyle(fontWeight: FontWeight.w600)),
                      if (cityName != null && cityName.isNotEmpty)
                        Text(cityName, style: const TextStyle(fontSize: 10)),
                    ],
                  ),
                  onSelected: (_) => _toggleZone(zoneId),
                  selectedColor: AirwayColors.primary.withAlpha(30),
                );
              }).toList(),
            ),
          if (_selectedZoneIds.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text('${_selectedZoneIds.length} working area(s) selected',
                style: TextStyle(color: AirwayColors.primary, fontWeight: FontWeight.w700)),
          ],
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
        Text(
          'Weekly Working Hours *',
          key: _scheduleKey,
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: _fieldErrors.containsKey('schedule') ? Colors.red : AirwayColors.text),
        ),
        if (_fieldErrors['schedule'] != null)
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Text(_fieldErrors['schedule']!, style: const TextStyle(color: Colors.red, fontSize: 12)),
          ),
        const SizedBox(height: 6),
        Text(AirwayText.tr('Choose the days and exact hours when you can accept jobs.', 'वे दिन और सही समय चुनें जब आप काम स्वीकार कर सकते हैं।'), style: TextStyle(color: AirwayColors.textSecondary)),
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
                        Expanded(child: OutlinedButton(onPressed: () => _pickScheduleTime(day, 'start'), child: Text(AirwayText.tr('From ${_timeText(_weeklySchedule[day]!['start']!)}', 'से: ${_timeText(_weeklySchedule[day]!['start']!)}')))),
                        const SizedBox(width: 8),
                        Expanded(child: OutlinedButton(onPressed: () => _pickScheduleTime(day, 'end'), child: Text(AirwayText.tr('To ${_timeText(_weeklySchedule[day]!['end']!)}', 'तक: ${_timeText(_weeklySchedule[day]!['end']!)}')))),
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
          key: _idDocumentKey,
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: _fieldErrors.containsKey('id_document') ? Colors.red : AirwayColors.text),
        ),
        if (_fieldErrors['id_document'] != null)
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Text(_fieldErrors['id_document']!, style: const TextStyle(color: Colors.red, fontSize: 12)),
          ),
        const SizedBox(height: 8),
        Text(
          AirwayText.tr('Please upload a valid government ID for verification. Aadhaar or any government-issued photo ID is accepted.', 'वेरिफ़िकेशन के लिए वैध सरकारी पहचान पत्र अपलोड करें। आधार या सरकार द्वारा जारी कोई भी फ़ोटो ID स्वीकार है।'),
          style: const TextStyle(color: AirwayColors.textSecondary),
        ),
        const SizedBox(height: 16),
        DropdownButtonFormField<String>(
          initialValue: _selectedIdType,
          items: [
            DropdownMenuItem(value: 'aadhaar', child: Text(AirwayText.tr('Aadhaar (Recommended)', 'आधार (अनुशंसित)'))),
            DropdownMenuItem(value: 'id', child: Text(AirwayText.tr('Other ID', 'अन्य पहचान पत्र'))),
          ],
          onChanged: (value) {
            if (value != null) {
              setState(() => _selectedIdType = value);
            }
          },
          decoration: InputDecoration(
            labelText: AirwayText.tr('ID Type', 'पहचान पत्र का प्रकार'),
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
              title: Text(AirwayText.tr('Document Submitted', 'दस्तावेज़ जमा हो गया'), style: TextStyle(color: Colors.green)),
              subtitle: Text(AirwayText.tr('Type: ${_selectedIdType.toUpperCase()}', 'प्रकार: ${_selectedIdType.toUpperCase()}')),
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
              subtitle: Text(AirwayText.tr('Type: ${_selectedIdType.toUpperCase()}', 'प्रकार: ${_selectedIdType.toUpperCase()}')),
            ),
          ),
        ],
        const SizedBox(height: 24),
        Text(
          AirwayText.tr('Note: Your application will be reviewed by our team. You will receive a notification once approved.', 'नोट: हमारी टीम आपके आवेदन की समीक्षा करेगी। स्वीकृति मिलने पर आपको नोटिफ़िकेशन मिलेगा।'),
          style: const TextStyle(color: AirwayColors.textSecondary, fontSize: 12),
        ),
      ],
    );
  }

  void _showIdDocDialog() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(AirwayText.tr('ID Document Already Uploaded', 'पहचान दस्तावेज़ पहले से अपलोड है')),
        content: const Text(
          'Your ID document has already been submitted and is pending review. '
          'You can replace it with a new document if needed. Your existing document will be updated.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text(AirwayText.tr('Keep Document', 'मौजूदा दस्तावेज़ रखें')),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              _pickIdDocument();
            },
            child: Text(AirwayText.tr('Upload New Document', 'नया दस्तावेज़ अपलोड करें')),
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
        const Divider(),
        _buildReviewItem('Equipment / products', _equipmentController.text.trim().isNotEmpty, _equipmentController.text.trim().isNotEmpty ? 'Added' : 'Optional'),
        const Divider(),
        _buildReviewItem('Bio', _bioController.text.trim().isNotEmpty, _bioController.text.trim().isNotEmpty ? 'Added' : 'Optional'),
        const SizedBox(height: 24),
        Card(
          color: Colors.amber,
          child: ListTile(
            leading: const Icon(Icons.info_outline),
            title: Text(AirwayText.tr('Important: Your application is subject to admin verification.', 'महत्वपूर्ण: आपका आवेदन एडमिन वेरिफ़िकेशन के अधीन है।')),
            subtitle: Text(AirwayText.tr('You will be notified via in-app notification once approved.', 'स्वीकृति मिलने पर ऐप में नोटिफ़िकेशन भेजा जाएगा।')),
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
          TextButton(onPressed: _goBack, child: Text(AirwayText.tr('Back', 'वापस')))
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
              child: Text(AirwayText.tr('Next', 'आगे'), style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
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
              child: Text(AirwayText.tr('Submit Application', 'आवेदन जमा करें'), style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
            ),
          ),
        ] else ...[
          Expanded(
            child: ElevatedButton(
              onPressed: _nextStep,
              style: ElevatedButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 16),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
              child: Text(AirwayText.tr('Next', 'आगे'), style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
            ),
          ),
        ],
      ],
    );
  }
}