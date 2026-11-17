import 'dart:async';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/notification/data/notification_api.dart';
import 'package:airway/features/notification/presentation/notification_list_screen.dart';

/// Shared customer/worker bell. The count comes from the server, not the
/// paginated inbox, so it remains accurate when unread items span pages.
class NotificationBellButton extends StatefulWidget {
  const NotificationBellButton({super.key, this.color = AirwayColors.text});
  final Color color;

  @override
  State<NotificationBellButton> createState() => _NotificationBellButtonState();
}

class _NotificationBellButtonState extends State<NotificationBellButton>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _rotation;
  StreamSubscription<RemoteMessage>? _foregroundSubscription;
  Timer? _refreshTimer;
  int _unreadCount = 0;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 620),
    );
    _rotation = TweenSequence<double>([
      TweenSequenceItem(tween: Tween(begin: 0, end: -.18), weight: 1),
      TweenSequenceItem(tween: Tween(begin: -.18, end: .16), weight: 2),
      TweenSequenceItem(tween: Tween(begin: .16, end: -.12), weight: 2),
      TweenSequenceItem(tween: Tween(begin: -.12, end: .08), weight: 2),
      TweenSequenceItem(tween: Tween(begin: .08, end: 0), weight: 1),
    ]).animate(CurvedAnimation(parent: _controller, curve: Curves.easeOut));
    _loadCount();
    _foregroundSubscription = FirebaseMessaging.onMessage.listen((_) {
      _controller.forward(from: 0);
      _loadCount();
    });
    _refreshTimer = Timer.periodic(
      const Duration(seconds: 45),
      (_) => _loadCount(),
    );
  }

  Future<void> _loadCount() async {
    try {
      final count = await NotificationApi.unreadCount();
      if (!mounted) return;
      if (count > _unreadCount) _controller.forward(from: 0);
      setState(() => _unreadCount = count);
    } catch (_) {
      // Keep the last known badge while offline; retry on the next refresh.
    }
  }

  Future<void> _openInbox() async {
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const NotificationListScreen()),
    );
    await _loadCount();
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    _foregroundSubscription?.cancel();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return IconButton(
      tooltip: _unreadCount == 0
          ? 'Notifications'
          : '$_unreadCount unread notifications',
      onPressed: _openInbox,
      icon: AnimatedBuilder(
        animation: _rotation,
        builder: (context, child) => Transform.rotate(
          angle: _rotation.value,
          child: child,
        ),
        child: SizedBox(
          width: 34,
          height: 34,
          child: Stack(
            clipBehavior: Clip.none,
            children: [
              Center(
                child: Icon(
                  Icons.notifications_none_rounded,
                  color: widget.color,
                  size: 25,
                ),
              ),
              if (_unreadCount > 0)
                Positioned(
                  right: -2,
                  top: -3,
                  child: Container(
                    constraints: const BoxConstraints(minWidth: 17, minHeight: 17),
                    padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
                    decoration: BoxDecoration(
                      color: AirwayColors.error,
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: Colors.white, width: 1.5),
                    ),
                    alignment: Alignment.center,
                    child: Text(
                      _unreadCount > 99 ? '99+' : '$_unreadCount',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 9,
                        fontWeight: FontWeight.w800,
                        height: 1.1,
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
