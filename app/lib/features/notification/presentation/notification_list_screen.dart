import 'package:flutter/material.dart' hide Notification;
import 'package:intl/intl.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/notification/data/notification_models.dart';
import 'package:airway/features/notification/data/notification_api.dart';
import 'package:airway/features/payment/presentation/payment_result_screen.dart';

class NotificationListScreen extends StatefulWidget {
  const NotificationListScreen({super.key});

  @override
  State<NotificationListScreen> createState() => _NotificationListScreenState();
}

class _NotificationListScreenState extends State<NotificationListScreen> {
  List<Notification> _notifications = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadNotifications();
  }

  Future<void> _loadNotifications() async {
    if (mounted) setState(() { _loading = true; _error = null; });
    try {
      final notifications = await NotificationApi.listNotifications();
      if (mounted) {
        setState(() {
          _notifications = notifications;
        });
      }
    } catch (e) {
      if (mounted) setState(() { _error = 'Could not load notifications.'; });
    } finally {
      if (mounted) setState(() { _loading = false; });
    }
  }

  Future<void> _refresh() async {
    await _loadNotifications();
  }

  Future<void> _markAllRead() async {
    try {
      await NotificationApi.markAllRead();
      await _loadNotifications();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to mark all as read: $e')),
        );
      }
    }
  }

  Future<void> _markRead(Notification notification) async {
    try {
      await NotificationApi.markRead(notification.id);
      if (mounted) {
        setState(() {
          final index = _notifications.indexWhere((n) => n.id == notification.id);
          if (index != -1) {
            final current = _notifications[index];
            _notifications[index] = Notification(
              id: current.id,
              type: current.type,
              title: current.title,
              body: current.body,
              channel: current.channel,
              isRead: true,
              readAt: DateTime.now(),
              createdAt: current.createdAt,
              data: current.data,
              bookingId: current.bookingId,
            );
          }
        });
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to mark as read: $e')),
        );
      }
    }
  }

  void _navigateToBooking(int? bookingId) {
    if (bookingId == null) return;
    // Navigate to payment result screen to view booking details
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (context) => PaymentResultScreen(bookingId: bookingId),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final unreadCount = _notifications.where((n) => !n.isRead).length;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Notifications'),
        actions: [
          if (unreadCount > 0)
            TextButton(
              onPressed: _markAllRead,
              child: const Text('Mark All Read'),
            ),
          IconButton(onPressed: _refresh, icon: const Icon(Icons.refresh)),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: _buildBody(),
      ),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_error != null) {
      return SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.error_outline, size: 48, color: AirwayColors.error),
                const SizedBox(height: 16),
                Text(_error!),
                const SizedBox(height: 16),
                FilledButton(onPressed: _loadNotifications, child: const Text('Retry')),
              ],
            ),
          ),
        ),
      );
    }

    if (_notifications.isEmpty) {
      return const Center(
        child: Text('No notifications yet'),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: _notifications.length,
      itemBuilder: (context, index) => _buildNotificationItem(_notifications[index]),
    );
  }

  Widget _buildNotificationItem(Notification notification) {
    final isRead = notification.isRead;
    final hasBookingId = notification.bookingId != null;

    return GestureDetector(
      onTap: hasBookingId ? () => _navigateToBooking(notification.bookingId) : null,
      child: Card(
        color: isRead ? null : AirwayColors.primarySoft,
        margin: const EdgeInsets.only(bottom: 8),
        child: ListTile(
          title: Text(
            notification.title,
            style: TextStyle(fontWeight: isRead ? FontWeight.normal : FontWeight.bold),
          ),
          subtitle: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(notification.body),
              const SizedBox(height: 4),
              Text(
                _formatTime(notification.createdAt),
                style: TextStyle(
                  fontSize: 12,
                  color: AirwayColors.textSecondary,
                ),
              ),
            ],
          ),
          trailing: !isRead
              ? IconButton(
                  icon: const Icon(Icons.check_circle_outline, color: AirwayColors.primary),
                  onPressed: () => _markRead(notification),
                )
              : const SizedBox.shrink(),
          leading: Icon(
            _getChannelIcon(notification.type),
            color: isRead ? AirwayColors.textSecondary : AirwayColors.primary,
          ),
        ),
      ),
    );
  }

  IconData _getChannelIcon(String type) {
    switch (type) {
      case NotificationType.bookingAssigned:
        return Icons.work;
      case NotificationType.bookingStarted:
        return Icons.play_arrow;
      case NotificationType.bookingCompleted:
        return Icons.check_circle;
      case NotificationType.bookingCancelled:
        return Icons.cancel;
      case NotificationType.paymentSuccess:
        return Icons.payment;
      case NotificationType.walletCredit:
        return Icons.account_balance_wallet;
      default:
        return Icons.notifications;
    }
  }

  String _formatTime(DateTime dt) {
    final now = DateTime.now();
    final diff = now.difference(dt);

    if (diff.inSeconds < 60) {
      return 'Just now';
    } else if (diff.inMinutes < 60) {
      return '${diff.inMinutes}m ago';
    } else if (diff.inHours < 24) {
      return '${diff.inHours}h ago';
    } else {
      return DateFormat('dd/MM/yyyy').format(dt);
    }
  }
}