import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/notification/data/push_notification_service.dart';

class NotificationPreferencesScreen extends StatefulWidget {
  const NotificationPreferencesScreen({super.key});

  @override
  State<NotificationPreferencesScreen> createState() =>
      _NotificationPreferencesScreenState();
}

class _NotificationPreferencesScreenState
    extends State<NotificationPreferencesScreen> {
  bool _enabled = true;
  bool _loading = true;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final enabled = await PushNotificationService.notificationsEnabled();
      if (mounted) setState(() => _enabled = enabled);
    } catch (_) {
      if (mounted) _message('Could not read notification permission status.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _change(bool value) async {
    if (_saving) return;
    setState(() => _saving = true);
    try {
      final applied = await PushNotificationService.setNotificationsEnabled(value);
      if (!mounted) return;
      if (!applied) {
        _message(
          'AIRway notification permission is blocked by your device. Enable it in your phone settings, then try again.',
        );
        await _load();
        return;
      }
      setState(() => _enabled = value);
      _message(value
          ? 'Push notifications enabled on this device.'
          : 'Push notifications disabled on this device.');
    } catch (error) {
      if (!mounted) return;
      _message(
        'Could not update notification settings. Check your connection and try again.',
      );
      await _load();
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  void _message(String value) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(value)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Notification preferences')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Card(
                  child: SwitchListTile.adaptive(
                    value: _enabled,
                    onChanged: _saving ? null : _change,
                    secondary: const Icon(
                      Icons.notifications_active_outlined,
                      color: AirwayColors.primary,
                    ),
                    title: const Text(
                      'Push notifications',
                      style: TextStyle(fontWeight: FontWeight.w700),
                    ),
                    subtitle: Text(
                      _saving
                          ? 'Updating this device…'
                          : 'Booking updates, payment alerts and service notifications on this device.',
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                const ListTile(
                  leading: Icon(Icons.inbox_outlined),
                  title: Text('In-app notification inbox'),
                  subtitle: Text(
                    'Your notification history remains available inside AIRway even when push notifications are turned off.',
                  ),
                ),
                const SizedBox(height: 8),
                const Text(
                  'This setting applies to the current device. Your other signed-in devices keep their own notification preference.',
                  style: TextStyle(
                    color: AirwayColors.textSecondary,
                    fontSize: 12,
                    height: 1.45,
                  ),
                ),
              ],
            ),
    );
  }
}
