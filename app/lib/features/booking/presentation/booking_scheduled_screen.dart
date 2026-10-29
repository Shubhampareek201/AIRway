import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_theme.dart';

class _Ui {
  static const violet = Color(0xFF6F4EF6);
  static const ink = Color(0xFF201A33);
  static const sub = Color(0xFF78718B);
  static const bg = Color(0xFFF8F7FD);
  static const pale = Color(0xFFF1EDFF);
  static const line = Color(0xFFEAE5F5);
}

class BookingScheduledScreen extends StatefulWidget {
  final int serviceId;
  final String serviceTitle;

  const BookingScheduledScreen({
    super.key,
    required this.serviceId,
    required this.serviceTitle,
  });

  @override
  State<BookingScheduledScreen> createState() => _BookingScheduledScreenState();
}

class _BookingScheduledScreenState extends State<BookingScheduledScreen> {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _Ui.bg,
      appBar: AppBar(
        title: Text(widget.serviceTitle),
        backgroundColor: _Ui.bg,
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.calendar_today_rounded, size: 64, color: _Ui.violet),
              const SizedBox(height: 20),
              Text(
                'Scheduled Booking',
                style: TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.w800,
                  color: _Ui.ink,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'Pick date & time for your service',
                style: TextStyle(color: _Ui.sub),
              ),
              const SizedBox(height: 24),
              FilledButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Go Back'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}