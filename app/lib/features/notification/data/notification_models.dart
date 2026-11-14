// Standalone model file - no part directive

class NotificationType {
  static const bookingConfirmed = 'booking_confirmed';
  static const bookingAssigned = 'booking_assigned';
  static const bookingStarted = 'booking_started';
  static const bookingCompleted = 'booking_completed';
  static const bookingCancelled = 'booking_cancelled';
  static const paymentSuccess = 'payment_success';
  static const walletCredit = 'wallet_credit';
  static const referralReward = 'referral_reward';
  static const workerBonus = 'worker_bonus';
  static const systemAnnouncement = 'system_announcement';
  static const workerOffer = 'worker_offer';
  static const workerOfferWithdrawn = 'worker_offer_withdrawn';
  static const workerOfferExpired = 'worker_offer_expired';

  static String getDisplay(String type) {
    switch (type) {
      case bookingConfirmed: return 'Booking Confirmed';
      case bookingAssigned: return 'Worker Assigned';
      case bookingStarted: return 'Service Started';
      case bookingCompleted: return 'Service Completed';
      case bookingCancelled: return 'Booking Cancelled';
      case paymentSuccess: return 'Payment Success';
      case walletCredit: return 'Wallet Credited';
      case referralReward: return 'Referral Reward';
      case workerBonus: return 'Worker Bonus';
      case systemAnnouncement: return 'System Announcement';
      case workerOffer: return 'Job Offer';
      case workerOfferWithdrawn: return 'Offer Withdrawn';
      case workerOfferExpired: return 'Offer Expired';
      default: return type;
    }
  }
}

class NotificationChannel {
  static const inApp = 'in_app';
  static const push = 'push';
  static const sms = 'sms';
  static const email = 'email';

  static String getDisplay(String channel) {
    switch (channel) {
      case inApp: return 'In-App';
      case push: return 'Push';
      case sms: return 'SMS';
      case email: return 'Email';
      default: return channel;
    }
  }
}

class Notification {
  final int id;
  final String type;
  final String title;
  final String body;
  final String channel;
  final bool isRead;
  final DateTime? readAt;
  final DateTime createdAt;
  final Map<String, dynamic>? data;
  final int? bookingId;

  Notification({
    required this.id,
    required this.type,
    required this.title,
    required this.body,
    required this.channel,
    required this.isRead,
    this.readAt,
    required this.createdAt,
    this.data,
    this.bookingId,
  });

  factory Notification.fromMap(Map<String, dynamic> map) {
    final data = map['data'] as Map<String, dynamic>?;
    return Notification(
      id: map['id'],
      type: map['type'],
      title: map['title'],
      body: map['body'],
      channel: map['channel'],
      isRead: map['is_read'] ?? false,
      readAt: map['read_at'] != null ? DateTime.parse(map['read_at']) : null,
      createdAt: DateTime.parse(map['created_at']),
      data: data,
      bookingId: data != null ? data['booking_id'] as int? : null,
    );
  }

  Map<String, dynamic> toMap() {
    return {
      'id': id,
      'type': type,
      'title': title,
      'body': body,
      'channel': channel,
      'is_read': isRead,
      'read_at': readAt?.toIso8601String(),
      'created_at': createdAt.toIso8601String(),
      'data': data,
    };
  }
}