import 'package:flutter/material.dart' hide Notification;
import 'package:airway/core/localization/airway_text.dart';
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
  final Set<int> _deletingIds = <int>{};
  final Set<int> _locallyDeletedIds = <int>{};
  bool _loading = true;
  String? _error;
  bool _markingAll = false;

  int get _unreadCount => _notifications.where((item) => !item.isRead).length;

  @override
  void initState() {
    super.initState();
    _loadNotifications();
  }

  Future<void> _loadNotifications({bool showLoader = true}) async {
    if (mounted) {
      setState(() {
        if (showLoader) _loading = true;
        _error = null;
      });
    }
    try {
      final notifications = await NotificationApi.listNotifications();
      if (mounted) {
        setState(() {
          // A refresh that started before a swipe must not reinsert an item
          // whose DELETE request has since succeeded.
          _notifications = notifications
              .where((item) =>
                  !_locallyDeletedIds.contains(item.id) &&
                  !_deletingIds.contains(item.id))
              .toList();
        });
      }
    } catch (_) {
      if (mounted) setState(() => _error = 'Could not load notifications. Please try again.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _markAllRead() async {
    if (_markingAll || _unreadCount == 0) return;
    setState(() => _markingAll = true);
    try {
      await NotificationApi.markAllRead();
      if (!mounted) return;
      setState(() {
        _notifications = _notifications.map((item) => _copyRead(item)).toList();
      });
    } catch (_) {
      if (mounted) _message('Could not mark notifications as read. Try again.');
    } finally {
      if (mounted) setState(() => _markingAll = false);
    }
  }

  Notification _copyRead(Notification item) => Notification(
    id: item.id,
    type: item.type,
    title: item.title,
    body: item.body,
    channel: item.channel,
    isRead: true,
    readAt: item.readAt ?? DateTime.now(),
    createdAt: item.createdAt,
    data: item.data,
    bookingId: item.bookingId,
  );

  Future<void> _markRead(Notification item) async {
    if (item.isRead) return;
    setState(() {
      final index = _notifications.indexWhere((n) => n.id == item.id);
      if (index >= 0) _notifications[index] = _copyRead(item);
    });
    try {
      await NotificationApi.markRead(item.id);
    } catch (_) {
      if (!mounted) return;
      setState(() {
        final index = _notifications.indexWhere((n) => n.id == item.id);
        if (index >= 0) _notifications[index] = item;
      });
      _message('Could not update this notification.');
    }
  }

  Future<void> _delete(Notification item) async {
    if (_deletingIds.contains(item.id) ||
        _locallyDeletedIds.contains(item.id)) {
      return;
    }

    // Remove immutably and immediately. Keep a tombstone so an overlapping
    // refresh cannot make the card reappear while DELETE is in flight.
    setState(() {
      _deletingIds.add(item.id);
      _notifications = _notifications
          .where((notification) => notification.id != item.id)
          .toList();
    });

    try {
      await NotificationApi.deleteNotification(item.id);
      if (!mounted) return;
      setState(() {
        _deletingIds.remove(item.id);
        _locallyDeletedIds.add(item.id);
      });
    } catch (_) {
      if (!mounted) return;

      // A timeout can happen after the server committed the DELETE. Reconcile
      // with the server before restoring the card, so a successful deletion
      // is never shown as a failure just because its response was lost.
      var stillExists = true;
      try {
        final latest = await NotificationApi.listNotifications();
        stillExists = latest.any((notification) => notification.id == item.id);
      } catch (_) {
        // If reconciliation is also offline, restore locally and let the user
        // retry; the next normal refresh will resolve the server state.
      }
      if (!mounted) return;

      if (!stillExists) {
        setState(() {
          _deletingIds.remove(item.id);
          _locallyDeletedIds.add(item.id);
          _notifications = _notifications
              .where((notification) => notification.id != item.id)
              .toList();
        });
        return;
      }

      setState(() {
        _deletingIds.remove(item.id);
        // Restore only this notification; do not overwrite other changes
        // that may have happened while the request was in flight.
        if (!_notifications.any((notification) => notification.id == item.id)) {
          _notifications = [..._notifications, item]
            ..sort((a, b) => b.createdAt.compareTo(a.createdAt));
        }
      });
      _message('Could not delete notification. Please try again.');
    }
  }

  void _message(String value) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(value), behavior: SnackBarBehavior.floating),
    );
  }

  Future<void> _openNotification(Notification item) async {
    await _markRead(item);
    if (!mounted || item.bookingId == null) return;
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => PaymentResultScreen(bookingId: item.bookingId!)),
    );
    if (mounted) _loadNotifications(showLoader: false);
  }

  String _sectionLabel(DateTime date) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final day = DateTime(date.year, date.month, date.day);
    if (day == today) return 'TODAY';
    if (day == today.subtract(const Duration(days: 1))) return 'YESTERDAY';
    return DateFormat('d MMMM yyyy').format(date).toUpperCase();
  }

  String _timeLabel(DateTime date) {
    final now = DateTime.now();
    final local = date.toLocal();
    if (now.difference(local).inHours < 24 && now.day == local.day) {
      return DateFormat('h:mm a').format(local);
    }
    return DateFormat('d MMM, h:mm a').format(local);
  }

  IconData _icon(String type) {
    switch (type) {
      case NotificationType.bookingConfirmed: return Icons.event_available_rounded;
      case NotificationType.bookingAssigned: return Icons.person_pin_circle_outlined;
      case NotificationType.bookingStarted: return Icons.play_circle_outline_rounded;
      case NotificationType.bookingCompleted: return Icons.task_alt_rounded;
      case NotificationType.bookingCancelled: return Icons.event_busy_rounded;
      case NotificationType.paymentSuccess: return Icons.payments_outlined;
      case NotificationType.walletCredit: return Icons.account_balance_wallet_outlined;
      case NotificationType.workerOffer: return Icons.work_outline_rounded;
      case NotificationType.workerOfferWithdrawn:
      case NotificationType.workerOfferExpired: return Icons.work_off_outlined;
      case NotificationType.referralReward:
      case NotificationType.workerBonus: return Icons.card_giftcard_rounded;
      case NotificationType.systemAnnouncement: return Icons.campaign_outlined;
      default: return Icons.notifications_active_outlined;
    }
  }

  Color _iconColor(String type) {
    if (type == NotificationType.paymentSuccess || type == NotificationType.walletCredit) {
      return const Color(0xFF16845B);
    }
    if (type == NotificationType.bookingCancelled || type == NotificationType.workerOfferExpired) {
      return AirwayColors.error;
    }
    return AirwayColors.primary;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AirwayColors.background,
      appBar: AppBar(
        titleSpacing: 20,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(AirwayText.tr('Notifications', 'सूचनाएँ'), style: TextStyle(fontWeight: FontWeight.w800)),
            Text(
              _unreadCount == 0 ? 'You are all caught up' : '$_unreadCount unread updates',
              style: const TextStyle(fontSize: 11, color: AirwayColors.textSecondary, fontWeight: FontWeight.w500),
            ),
          ],
        ),
        actions: [
          if (_unreadCount > 0)
            TextButton(
              onPressed: _markingAll ? null : _markAllRead,
              child: _markingAll
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                  : Text(AirwayText.tr('Mark all read', 'सभी को पढ़ा हुआ करें')),
            ),
          IconButton(
            tooltip: 'Refresh',
            onPressed: () => _loadNotifications(),
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => _loadNotifications(),
        child: _buildBody(),
      ),
    );
  }

  Widget _buildBody() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          const SizedBox(height: 130),
          Icon(Icons.cloud_off_rounded, size: 46, color: AirwayColors.textSecondary.withValues(alpha: .65)),
          const SizedBox(height: 14),
          Center(child: Text(_error!, textAlign: TextAlign.center)),
          const SizedBox(height: 14),
          Center(child: FilledButton.icon(onPressed: () => _loadNotifications(), icon: const Icon(Icons.refresh), label: Text(AirwayText.tr('Try again', 'फिर कोशिश करें')))),
        ],
      );
    }
    if (_notifications.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          const SizedBox(height: 110),
          Center(
            child: Container(
              width: 88,
              height: 88,
              decoration: BoxDecoration(color: AirwayColors.primary.withValues(alpha: .09), shape: BoxShape.circle),
              child: const Icon(Icons.notifications_off_outlined, size: 40, color: AirwayColors.primary),
            ),
          ),
          const SizedBox(height: 18),
          Center(child: Text(AirwayText.tr('Nothing new right now', 'अभी कोई नई सूचना नहीं है'), style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800))),
          const SizedBox(height: 7),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 38),
            child: Text(AirwayText.tr('Booking updates, payment receipts and important alerts will appear here.', 'बुकिंग अपडेट, भुगतान रसीदें और ज़रूरी सूचनाएँ यहाँ दिखाई देंगी।'), textAlign: TextAlign.center, style: TextStyle(color: AirwayColors.textSecondary, height: 1.45)),
          ),
        ],
      );
    }

    final sections = <String, List<Notification>>{};
    for (final item in _notifications) {
      sections.putIfAbsent(_sectionLabel(item.createdAt), () => []).add(item);
    }
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 28),
      children: [
        if (_unreadCount > 0)
          Padding(
            padding: const EdgeInsets.only(bottom: 14),
            child: Row(
              children: [
                Container(width: 7, height: 7, decoration: const BoxDecoration(color: AirwayColors.primary, shape: BoxShape.circle)),
                const SizedBox(width: 8),
                Text('$_unreadCount UNREAD', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w800, letterSpacing: .8, color: AirwayColors.primary)),
              ],
            ),
          ),
        for (final entry in sections.entries) ...[
          Padding(
            padding: const EdgeInsets.fromLTRB(2, 12, 2, 9),
            child: Text(entry.key, style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w800, letterSpacing: 1.05, color: AirwayColors.textSecondary)),
          ),
          for (final item in entry.value) _notificationCard(item),
        ],
      ],
    );
  }

  Widget _notificationCard(Notification item) {
    final unread = !item.isRead;
    final tint = _iconColor(item.type);
    return Dismissible(
      key: ValueKey(item.id),
      direction: DismissDirection.endToStart,
      background: Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.only(right: 22),
        alignment: Alignment.centerRight,
        decoration: BoxDecoration(color: AirwayColors.error, borderRadius: BorderRadius.circular(17)),
        child: const Icon(Icons.delete_outline_rounded, color: Colors.white),
      ),
      onDismissed: (_) => _delete(item),
      child: InkWell(
        onTap: () => _openNotification(item),
        borderRadius: BorderRadius.circular(17),
        child: Container(
          margin: const EdgeInsets.only(bottom: 10),
          padding: const EdgeInsets.fromLTRB(13, 13, 12, 13),
          decoration: BoxDecoration(
            color: unread ? AirwayColors.primary.withValues(alpha: .055) : Colors.white,
            borderRadius: BorderRadius.circular(17),
            border: Border.all(
              color: unread ? AirwayColors.primary.withValues(alpha: .24) : const Color(0xFFEAECEF),
            ),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 42,
                height: 42,
                decoration: BoxDecoration(color: tint.withValues(alpha: .11), borderRadius: BorderRadius.circular(13)),
                child: Icon(_icon(item.type), color: tint, size: 21),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: Text(
                            item.title,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(fontSize: 13.5, height: 1.3, fontWeight: unread ? FontWeight.w800 : FontWeight.w600, color: AirwayColors.text),
                          ),
                        ),
                        if (unread) ...[
                          const SizedBox(width: 7),
                          Container(width: 7, height: 7, margin: const EdgeInsets.only(top: 5), decoration: const BoxDecoration(color: AirwayColors.primary, shape: BoxShape.circle)),
                        ],
                      ],
                    ),
                    if (item.body.trim().isNotEmpty) ...[
                      const SizedBox(height: 5),
                      Text(
                        item.body,
                        maxLines: 3,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 12, height: 1.4, color: AirwayColors.textSecondary),
                      ),
                    ],
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Icon(Icons.access_time_rounded, size: 12, color: AirwayColors.textSecondary.withValues(alpha: .8)),
                        const SizedBox(width: 4),
                        Text(_timeLabel(item.createdAt), style: const TextStyle(fontSize: 10.5, color: AirwayColors.textSecondary)),
                        const Spacer(),
                        if (item.bookingId != null)
                          Text(AirwayText.tr('VIEW BOOKING', 'बुकिंग देखें'), style: TextStyle(fontSize: 9, fontWeight: FontWeight.w800, letterSpacing: .5, color: AirwayColors.primary)),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
