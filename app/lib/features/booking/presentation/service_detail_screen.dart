import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_theme.dart';
import 'package:airway/features/booking/presentation/booking_scheduled_screen.dart';

class _Ui {
  static const violet = Color(0xFF6F4EF6);
  static const ink = Color(0xFF201A33);
  static const sub = Color(0xFF78718B);
  static const bg = Color(0xFFF8F7FD);
  static const pale = Color(0xFFF1EDFF);
  static const line = Color(0xFFEAE5F5);
}

class ServiceDetailScreen extends StatefulWidget {
  final int serviceId;
  final String serviceTitle;

  const ServiceDetailScreen({
    super.key,
    required this.serviceId,
    required this.serviceTitle,
  });

  @override
  State<ServiceDetailScreen> createState() => _ServiceDetailScreenState();
}

class _ServiceDetailScreenState extends State<ServiceDetailScreen> {
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
              Icon(Icons.construction_rounded, size: 64, color: _Ui.violet),
              const SizedBox(height: 20),
              Text(
                'Service Detail Screen',
                style: TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.w800,
                  color: _Ui.ink,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'Loading service details from API...',
                style: TextStyle(color: _Ui.sub),
              ),
              const SizedBox(height: 24),
              FilledButton(
                onPressed: () {
                  Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) => BookingScheduledScreen(
                        serviceId: widget.serviceId,
                        serviceTitle: widget.serviceTitle,
                      ),
                    ),
                  );
                },
                child: const Text('Book Now'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}