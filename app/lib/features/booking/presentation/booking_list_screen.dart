import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_theme.dart';

class _Ui {
  static const violet = Color(0xFF7861A8);
  static const ink = Color(0xFF292331);
  static const sub = Color(0xFF81788A);
  static const bg = Color(0xFFF7F3EC);
  static const pale = Color(0xFFEDE7F5);
  static const line = Color(0xFFE8E0ED);
}

class BookingListScreen extends StatefulWidget {
  const BookingListScreen({super.key});

  @override
  State<BookingListScreen> createState() => _BookingListScreenState();
}

class _BookingListScreenState extends State<BookingListScreen> {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _Ui.bg,
      appBar: AppBar(
        title: const Text('My Bookings'),
        backgroundColor: _Ui.bg,
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.history_rounded, size: 64, color: _Ui.violet),
              const SizedBox(height: 20),
              Text(
                'My Bookings',
                style: TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.w800,
                  color: _Ui.ink,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'Your bookings will appear here',
                style: TextStyle(color: _Ui.sub),
              ),
            ],
          ),
        ),
      ),
    );
  }
}