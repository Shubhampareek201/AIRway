import 'package:flutter/material.dart';

class AirwayColors {
  AirwayColors._();

  static const primary = Color(0xFF7154E8);
  static const primaryDark = Color(0xFF5135C5);
  static const lavender = Color(0xFFF0EDFF);
  static const background = Color(0xFFF8F7FC);
  static const surface = Colors.white;
  static const text = Color(0xFF211B35);
  static const muted = Color(0xFF756F85);
  static const border = Color(0xFFE8E4F1);
}
class AirwayTheme {
  AirwayTheme._();

  static ThemeData get light {
    final scheme = ColorScheme.fromSeed(
      seedColor: AirwayColors.primary,
      brightness: Brightness.light,
    ).copyWith(
      primary: AirwayColors.primary,
      onPrimary: Colors.white,
      surface: AirwayColors.surface,
      onSurface: AirwayColors.text,
      outline: AirwayColors.border,
      surfaceContainerLowest: AirwayColors.surface,
      surfaceContainerLow: AirwayColors.background,
    );

    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      colorScheme: scheme,
      scaffoldBackgroundColor: AirwayColors.background,
      appBarTheme: const AppBarTheme(
        backgroundColor: AirwayColors.background,
        foregroundColor: AirwayColors.text,
        elevation: 0,
        centerTitle: false,
        titleTextStyle: TextStyle(
          fontSize: 20,
          fontWeight: FontWeight.w700,
          color: AirwayColors.text,
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: AirwayColors.primary,
          foregroundColor: Colors.white,
          minimumSize: const Size(0, 52),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          textStyle: const TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AirwayColors.primary,
          minimumSize: const Size(0, 52),
          side: const BorderSide(color: AirwayColors.border),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: AirwayColors.surface,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 16,
          vertical: 16,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(
            color: AirwayColors.border,
          ),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(
            color: AirwayColors.border,
          ),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(
            color: AirwayColors.primary,
            width: 1.5,
          ),
        ),
      ),
      cardTheme: CardThemeData(
        color: AirwayColors.surface,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
          side: const BorderSide(
            color: AirwayColors.border,
          ),
        ),
      ),
      bottomSheetTheme: const BottomSheetThemeData(
        backgroundColor: AirwayColors.surface,
        showDragHandle: true,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(
            top: Radius.circular(24),
          ),
        ),
      ),
      navigationBarTheme: const NavigationBarThemeData(
        backgroundColor: AirwayColors.surface,
        indicatorColor: AirwayColors.lavender,
      ),
    );
  }
}
