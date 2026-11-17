import 'package:flutter/material.dart';
import 'package:airway/core/localization/airway_text.dart';
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
      if (mounted) _message(AirwayText.tr('Could not read notification permission status.', 'नोटिफ़िकेशन अनुमति की स्थिति नहीं पढ़ी जा सकी।'));
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
          AirwayText.tr('AIRway notification permission is blocked by your device. Enable it in your phone settings, then try again.', 'इस डिवाइस पर AIRway नोटिफ़िकेशन की अनुमति बंद है। फ़ोन सेटिंग्स में इसे चालू करके फिर कोशिश करें।'),
        );
        await _load();
        return;
      }
      setState(() => _enabled = value);
      _message(value
          ? AirwayText.tr('Push notifications enabled on this device.', 'इस डिवाइस पर पुश नोटिफ़िकेशन चालू हैं।')
          : AirwayText.tr('Push notifications disabled on this device.', 'इस डिवाइस पर पुश नोटिफ़िकेशन बंद हैं।'));
    } catch (error) {
      if (!mounted) return;
      _message(
        AirwayText.tr('Could not update notification settings. Check your connection and try again.', 'नोटिफ़िकेशन सेटिंग्स अपडेट नहीं हो सकीं। कनेक्शन जाँचकर फिर कोशिश करें।'),
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
      appBar: AppBar(title: Text(AirwayText.tr('Notification preferences', 'नोटिफ़िकेशन प्राथमिकताएँ'))),
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
                    title: Text(
                      AirwayText.tr('Push notifications', 'पुश नोटिफ़िकेशन'),
                      style: TextStyle(fontWeight: FontWeight.w700),
                    ),
                    subtitle: Text(
                      _saving
                          ? AirwayText.tr('Updating this device…', 'इस डिवाइस को अपडेट किया जा रहा है…')
                          : AirwayText.tr('Booking updates, payment alerts and service notifications on this device.', 'इस डिवाइस पर बुकिंग अपडेट, पेमेंट अलर्ट और सेवा नोटिफ़िकेशन।'),
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                ListTile(
                  leading: const Icon(Icons.inbox_outlined),
                  title: Text(AirwayText.tr('In-app notification inbox', 'ऐप के अंदर नोटिफ़िकेशन इनबॉक्स')),
                  subtitle: Text(
                    AirwayText.tr('Your notification history remains available inside AIRway even when push notifications are turned off.', 'पुश नोटिफ़िकेशन बंद होने पर भी आपका नोटिफ़िकेशन इतिहास AIRway में उपलब्ध रहेगा।'),
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  AirwayText.tr('This setting applies to the current device. Your other signed-in devices keep their own notification preference.', 'यह सेटिंग केवल इस डिवाइस पर लागू होती है। दूसरे डिवाइस की नोटिफ़िकेशन सेटिंग अलग रहेगी।'),
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
