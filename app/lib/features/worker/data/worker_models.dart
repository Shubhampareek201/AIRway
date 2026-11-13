// Standalone model file - no part directive

double? _parseWorkerRating(dynamic value) {
  if (value == null) return null;
  final parsed = value is num ? value.toDouble() : double.tryParse(value.toString().trim());
  return parsed != null && parsed.isFinite ? parsed : null;
}

String workerCustomerAnswerLabel(String key, dynamic value) {
  if (key == 'professional_preference') {
    return value?.toString() == 'female'
        ? 'Professional requirement: Female professional'
        : 'Professional requirement: No preference';
  }
  return '${key.replaceAll('_', ' ')}: $value';
}

class WorkerProfile {
  final int? id;
  final String status;
  final String? name;
  final String? phone;
  final String? upiId;
  final bool isOnline;
  final double? ratingAvg;
  final int? experienceYears;
  final String? rejectionReason;
  final String? qualification;
  final String? equipmentDetails;
  final String? residentialAddress;
  final String? landmark;
  final String? bio;
  final String? photoUrl;
  final List<Map<String, dynamic>> serviceItems;
  final List<String> services;
  final List<String> zones;
  final List<Map<String, dynamic>> schedules;
  final List<Map<String, dynamic>> documents;

  WorkerProfile({
    this.id,
    required this.status,
    this.name,
    this.phone,
    this.upiId,
    required this.isOnline,
    this.ratingAvg,
    this.experienceYears,
    this.rejectionReason,
    this.qualification,
    this.equipmentDetails,
    this.residentialAddress,
    this.landmark,
    this.bio,
    this.photoUrl,
    this.serviceItems = const [],
    this.services = const [],
    this.zones = const [],
    this.schedules = const [],
    this.documents = const [],
  });

  factory WorkerProfile.fromMap(Map<String, dynamic> map) {
    return WorkerProfile(
      id: map['id'] as int?,
      status: map['status'] as String? ?? 'pending',
      name: map['name'] as String?,
      phone: map['phone'] as String?,
      upiId: map['upi_id'] as String?,
      isOnline: map['is_online'] as bool? ?? false,
      ratingAvg: _parseWorkerRating(map['rating_avg']),
      experienceYears: map['experience_years'] as int?,
      rejectionReason: map['rejection_reason'] as String?,
      qualification: map['qualification'] as String?,
      equipmentDetails: map['equipment_details'] as String?,
      residentialAddress: map['residential_address'] as String?,
      landmark: map['landmark'] as String?,
      bio: map['bio'] as String?,
      photoUrl: map['photo_url']?.toString(),
      serviceItems: (map['services'] as List? ?? [])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList(),
      services: (map['services'] as List? ?? [])
          .whereType<Map>()
          .map((item) => item['service_title']?.toString() ?? '')
          .where((value) => value.isNotEmpty)
          .toList(),
      zones: (map['zones'] as List? ?? [])
          .whereType<Map>()
          .map((item) => item['zone_name']?.toString() ?? '')
          .where((value) => value.isNotEmpty)
          .toList(),
      schedules: (map['schedules'] as List? ?? [])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList(),
      documents: (map['documents'] as List? ?? [])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList(),
    );
  }
}

class WorkerOffer {
  static const pending = 'pending';
  static const accepted = 'accepted';
  static const declined = 'declined';
  static const expired = 'expired';
  static const withdrawn = 'withdrawn';

  final int id;
  final int bookingId;
  final String status;
  final String statusDisplay;
  final DateTime offeredAt;
  final DateTime? expiresAt;
  final String? workerName;
  final String? workerPhone;
  final String? serviceTitle;
  final String? variantTitle;
  final DateTime? scheduledAt;
  final String? serviceAddress;
  final Map<String, dynamic> customerAnswers;
  final List<Map<String, dynamic>> formResponses;
  final List<Map<String, dynamic>> addons;
  final int quantity;
  final bool canAccept;
  final bool canDecline;
  final bool canWithdraw;

  WorkerOffer({
    required this.id,
    required this.bookingId,
    required this.status,
    required this.statusDisplay,
    required this.offeredAt,
    this.expiresAt,
    this.workerName,
    this.workerPhone,
    this.serviceTitle,
    this.variantTitle,
    this.scheduledAt,
    this.serviceAddress,
    this.customerAnswers = const {},
    this.formResponses = const [],
    this.addons = const [],
    this.quantity = 1,
    required this.canAccept,
    required this.canDecline,
    required this.canWithdraw,
  });

  factory WorkerOffer.fromMap(Map<String, dynamic> map) {
    return WorkerOffer(
      id: map['id'] as int,
      bookingId: map['booking'] as int,
      status: map['status'] as String? ?? '',
      statusDisplay: map['status_display'] as String? ?? '',
      offeredAt: DateTime.parse(map['offered_at'] as String),
      expiresAt: map['expires_at'] != null ? DateTime.parse(map['expires_at'] as String) : null,
      workerName: map['worker_name'] as String?,
      workerPhone: map['worker_phone'] as String?,
      serviceTitle: map['service_title'] as String?,
      variantTitle: map['variant_title'] as String?,
      scheduledAt: map['scheduled_at'] != null ? DateTime.parse(map['scheduled_at'] as String) : null,
      serviceAddress: map['service_address'] as String?,
      customerAnswers: Map<String, dynamic>.from(map['customer_answers'] as Map? ?? {}),
      formResponses: (map['form_responses'] as List? ?? []).map((e) => Map<String, dynamic>.from(e)).toList(),
      addons: (map['addons'] as List? ?? []).map((e) => Map<String, dynamic>.from(e)).toList(),
      quantity: int.tryParse(map['quantity']?.toString() ?? '1') ?? 1,
      canAccept: map['can_accept'] as bool? ?? false,
      canDecline: map['can_decline'] as bool? ?? false,
      canWithdraw: map['can_withdraw'] as bool? ?? false,
    );
  }
}

class WorkerJob {
  final int id;
  final int bookingId;
  final String status;
  final String serviceTitle;
  final String customerName;
  final String? customerPhone;
  final String? address;
  final DateTime scheduledAt;
  final DateTime? dropScheduledAt;
  final double amount;
  final DateTime? assignedAt;

  WorkerJob({
    required this.id,
    required this.bookingId,
    required this.status,
    required this.serviceTitle,
    required this.customerName,
    this.customerPhone,
    this.address,
    required this.scheduledAt,
    this.dropScheduledAt,
    required this.amount,
    this.assignedAt,
  });

  factory WorkerJob.fromMap(Map<String, dynamic> map) {
    return WorkerJob(
      id: map['id'],
      bookingId: map['booking_id'],
      status: map['status'] ?? '',
      serviceTitle: map['service_title'] ?? '',
      customerName: map['customer_name'] ?? '',
      customerPhone: map['customer_phone'],
      address: map['address'],
      scheduledAt: DateTime.parse(map['scheduled_at']),
      dropScheduledAt: map['drop_scheduled_at'] != null ? DateTime.parse(map['drop_scheduled_at']) : null,
      amount: double.tryParse(map['amount'].toString()) ?? 0.0,
      assignedAt: map['assigned_at'] != null ? DateTime.parse(map['assigned_at']) : null,
    );
  }
}

class WorkerAssignmentDetail {
  final int assignmentId;
  final int bookingId;
  final String bookingIdStr;
  final String status;
  final String serviceTitle;
  final String customerName;
  final String? customerPhone;
  final String? address;
  final DateTime scheduledAt;
  final DateTime? dropScheduledAt;
  final double amount;
  final String? paymentLabel;
  final String? notes;
  final String? workerNotes;
  final List<Map<String, dynamic>> formResponses;
  final Map<String, dynamic> customerAnswers;
  final String? variantTitle;
  final int quantity;
  final List<Map<String, dynamic>> addons;
  final WorkerAssignmentInfo assignment;

  WorkerAssignmentDetail({
    required this.assignmentId,
    required this.bookingId,
    required this.bookingIdStr,
    required this.status,
    required this.serviceTitle,
    required this.customerName,
    this.customerPhone,
    this.address,
    required this.scheduledAt,
    this.dropScheduledAt,
    required this.amount,
    this.paymentLabel,
    this.notes,
    this.workerNotes,
    required this.formResponses,
    this.customerAnswers = const {},
    this.variantTitle,
    this.quantity = 1,
    this.addons = const [],
    required this.assignment,
  });

  factory WorkerAssignmentDetail.fromMap(Map<String, dynamic> map) {
    return WorkerAssignmentDetail(
      assignmentId: map['id'] as int,
      bookingId: map['booking_id'] as int,
      bookingIdStr: map['id'].toString(),
      status: map['status'] ?? '',
      serviceTitle: map['service_title'] ?? '',
      customerName: map['customer_name'] ?? '',
      customerPhone: map['customer_phone'],
      address: map['address'],
      scheduledAt: DateTime.parse(map['scheduled_at']),
      dropScheduledAt: map['drop_scheduled_at'] != null ? DateTime.parse(map['drop_scheduled_at']) : null,
      amount: double.tryParse(map['amount'].toString()) ?? 0.0,
      paymentLabel: map['payment_label']?.toString(),
      notes: map['notes'],
      workerNotes: map['worker_notes'],
      formResponses: (map['form_responses'] as List? ?? []).map((e) => Map<String, dynamic>.from(e)).toList(),
      customerAnswers: Map<String, dynamic>.from(map['customer_answers'] as Map? ?? {}),
      variantTitle: map['variant_title']?.toString(),
      quantity: int.tryParse(map['quantity']?.toString() ?? '1') ?? 1,
      addons: (map['addons'] as List? ?? []).map((e) => Map<String, dynamic>.from(e)).toList(),
      assignment: WorkerAssignmentInfo.fromMap(map['assignment']),
    );
  }
}

class WorkerAssignmentInfo {
  final DateTime? assignedAt;
  final DateTime? acceptedAt;
  final DateTime? startedAt;
  final DateTime? completedAt;

  WorkerAssignmentInfo({
    this.assignedAt,
    this.acceptedAt,
    this.startedAt,
    this.completedAt,
  });

  factory WorkerAssignmentInfo.fromMap(Map<String, dynamic> map) {
    return WorkerAssignmentInfo(
      assignedAt: map['assigned_at'] != null ? DateTime.parse(map['assigned_at']) : null,
      acceptedAt: map['accepted_at'] != null ? DateTime.parse(map['accepted_at']) : null,
      startedAt: map['started_at'] != null ? DateTime.parse(map['started_at']) : null,
      completedAt: map['completed_at'] != null ? DateTime.parse(map['completed_at']) : null,
    );
  }

  String get statusDisplay {
    if (completedAt != null) return 'Completed';
    if (startedAt != null) return 'In Progress';
    if (acceptedAt != null) return 'Accepted';
    if (assignedAt != null) return 'Assigned';
    return 'Pending';
  }
}