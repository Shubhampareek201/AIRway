class BookingStatus {
  static const pending = 'pending';
  static const confirmed = 'confirmed';
  static const assigned = 'assigned';
  static const inProgress = 'in_progress';
  static const completed = 'completed';
  static const cancelled = 'cancelled';
  static const disputed = 'disputed';

  static String display(String status) {
    switch (status) {
      case pending:
        return 'Pending';
      case confirmed:
        return 'Confirmed';
      case assigned:
        return 'Assigned';
      case inProgress:
        return 'In Progress';
      case completed:
        return 'Completed';
      case cancelled:
        return 'Cancelled';
      case disputed:
        return 'Disputed';
      default:
        return status;
    }
  }
}

class PaymentMethod {
  static const cod = 'cod';
  static const razorpay = 'razorpay';

  static String display(String method) {
    switch (method) {
      case cod:
        return 'Cash on Delivery';
      case razorpay:
        return 'Razorpay';
      default:
        return method;
    }
  }
}

class Booking {
  final int id;
  final int serviceId;
  final String serviceTitle;
  final String? serviceImage;
  final int? variantId;
  final String? variantTitle;
  final String bookingMode;
  final String status;
  final DateTime scheduledAt;
  final DateTime? dropScheduledAt;
  final Map<String, dynamic> pricingSnapshot;
  final List<BookingAddOn> addons;
  final List<BookingFormResponse> formResponses;
  final List<BookingStatusHistory> statusHistory;
  final BookingAssignment? assignment;
  final bool canCancel;

  Booking({
    required this.id,
    required this.serviceId,
    required this.serviceTitle,
    this.serviceImage,
    this.variantId,
    this.variantTitle,
    required this.bookingMode,
    required this.status,
    required this.scheduledAt,
    this.dropScheduledAt,
    required this.pricingSnapshot,
    required this.addons,
    required this.formResponses,
    required this.statusHistory,
    this.assignment,
    required this.canCancel,
  });

  double get totalAmount {
    final total = pricingSnapshot['total'];
    if (total == null) return 0.0;
    return double.tryParse(total.toString()) ?? 0.0;
  }

  String get scheduledAtDisplay {
    return scheduledAt.toLocal().toString().substring(0, 16).replaceAll('T', ' ');
  }

  factory Booking.fromMap(Map<String, dynamic> map) {
    return Booking(
      id: map['id'],
      serviceId: map['service'],
      serviceTitle: map['service_title'] ?? '',
      serviceImage: map['service_image'],
      variantId: map['variant'],
      variantTitle: map['variant_title'],
      bookingMode: map['booking_mode'],
      status: map['status'],
      scheduledAt: DateTime.parse(map['scheduled_at']),
      dropScheduledAt: map['drop_scheduled_at'] != null
          ? DateTime.parse(map['drop_scheduled_at'])
          : null,
      pricingSnapshot: Map<String, dynamic>.from(map['pricing_snapshot'] ?? {}),
      addons: (map['addons'] as List? ?? [])
          .map((e) => BookingAddOn.fromMap(Map<String, dynamic>.from(e)))
          .toList(),
      formResponses: (map['form_responses'] as List? ?? [])
          .map((e) => BookingFormResponse.fromMap(Map<String, dynamic>.from(e)))
          .toList(),
      statusHistory: (map['status_history'] as List? ?? [])
          .map((e) => BookingStatusHistory.fromMap(Map<String, dynamic>.from(e)))
          .toList(),
      assignment: map['assignment'] != null
          ? BookingAssignment.fromMap(Map<String, dynamic>.from(map['assignment']))
          : null,
      canCancel: map['can_cancel'] ?? false,
    );
  }
}

class BookingAddOn {
  final int id;
  final int addonId;
  final String addonTitle;
  final int quantity;
  final double unitPrice;
  final double totalPrice;

  BookingAddOn({
    required this.id,
    required this.addonId,
    required this.addonTitle,
    required this.quantity,
    required this.unitPrice,
    required this.totalPrice,
  });

  factory BookingAddOn.fromMap(Map<String, dynamic> map) {
    return BookingAddOn(
      id: map['id'],
      addonId: map['addon'],
      addonTitle: map['addon_title'] ?? '',
      quantity: map['quantity'] ?? 1,
      unitPrice: double.tryParse(map['unit_price'].toString()) ?? 0,
      totalPrice: double.tryParse(map['total_price'].toString()) ?? 0,
    );
  }
}

class BookingFormResponse {
  final int id;
  final int formFieldId;
  final String fieldKey;
  final String fieldLabel;
  final String fieldType;
  final dynamic value;

  BookingFormResponse({
    required this.id,
    required this.formFieldId,
    required this.fieldKey,
    required this.fieldLabel,
    required this.fieldType,
    required this.value,
  });

  factory BookingFormResponse.fromMap(Map<String, dynamic> map) {
    return BookingFormResponse(
      id: map['id'],
      formFieldId: map['form_field'],
      fieldKey: map['field_key'] ?? '',
      fieldLabel: map['field_label'] ?? '',
      fieldType: map['field_type'] ?? '',
      value: map['value'],
    );
  }
}

class BookingStatusHistory {
  final int id;
  final String fromStatus;
  final String toStatus;
  final String? changedByName;
  final String note;
  final DateTime createdAt;

  BookingStatusHistory({
    required this.id,
    required this.fromStatus,
    required this.toStatus,
    this.changedByName,
    required this.note,
    required this.createdAt,
  });

  factory BookingStatusHistory.fromMap(Map<String, dynamic> map) {
    return BookingStatusHistory(
      id: map['id'],
      fromStatus: map['from_status'] ?? '',
      toStatus: map['to_status'],
      changedByName: map['changed_by_name'],
      note: map['note'] ?? '',
      createdAt: DateTime.parse(map['created_at']),
    );
  }
}

class BookingAssignment {
  final int id;
  final int workerId;
  final String workerName;
  final String workerPhone;
  final double? workerRating;
  final String? workerPhoto;
  final DateTime assignedAt;
  final DateTime? acceptedAt;
  final DateTime? startedAt;
  final DateTime? completedAt;

  BookingAssignment({
    required this.id,
    required this.workerId,
    required this.workerName,
    required this.workerPhone,
    this.workerRating,
    this.workerPhoto,
    required this.assignedAt,
    this.acceptedAt,
    this.startedAt,
    this.completedAt,
  });

  factory BookingAssignment.fromMap(Map<String, dynamic> map) {
    return BookingAssignment(
      id: map['id'],
      workerId: map['worker'],
      workerName: map['worker_name'] ?? '',
      workerPhone: map['worker_phone'] ?? '',
      workerRating: map['worker_rating'] != null
          ? double.tryParse(map['worker_rating'].toString())
          : null,
      workerPhoto: map['worker_photo'],
      assignedAt: DateTime.parse(map['assigned_at']),
      acceptedAt: map['accepted_at'] != null
          ? DateTime.parse(map['accepted_at'])
          : null,
      startedAt: map['started_at'] != null
          ? DateTime.parse(map['started_at'])
          : null,
      completedAt: map['completed_at'] != null
          ? DateTime.parse(map['completed_at'])
          : null,
    );
  }
}