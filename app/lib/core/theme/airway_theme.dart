import 'package:flutter/material.dart';
import 'airway_colors.dart';

class AirwayTheme {
  AirwayTheme._();

  static final ColorScheme _scheme = ColorScheme.fromSeed(
    seedColor: AirwayColors.sage,
    brightness: Brightness.light,
  ).copyWith(
    primary: AirwayColors.sage,
    onPrimary: Colors.white,
    secondary: AirwayColors.clay,
    onSecondary: Colors.white,
    surface: AirwayColors.surface,
    onSurface: AirwayColors.text,
    outline: AirwayColors.border,
    surfaceContainerLowest: AirwayColors.surface,
    surfaceContainerLow: AirwayColors.background,
  );

  static ThemeData get light {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      colorScheme: _scheme,
      scaffoldBackgroundColor: AirwayColors.background,
      splashFactory: NoSplash.splashFactory,
      highlightColor: Colors.transparent,
      hoverColor: AirwayColors.surfaceVariant,
      appBarTheme: const AppBarTheme(
        backgroundColor: Colors.transparent,
        foregroundColor: AirwayColors.text,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: false,
        titleTextStyle: TextStyle(
          fontSize: 20,
          fontWeight: FontWeight.w700,
          color: AirwayColors.text,
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: AirwayColors.sage,
          foregroundColor: Colors.white,
          minimumSize: const Size(0, 52),
          shape: const ContinuousRectangleBorder(
            borderRadius: BorderRadius.all(Radius.circular(16)),
          ),
          textStyle: const TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w600,
            letterSpacing: 0.2,
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AirwayColors.sage,
          minimumSize: const Size(0, 52),
          side: const BorderSide(color: AirwayColors.border),
          shape: const ContinuousRectangleBorder(
            borderRadius: BorderRadius.all(Radius.circular(16)),
          ),
          textStyle: const TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: AirwayColors.sage,
          textStyle: const TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      inputDecorationTheme: const InputDecorationTheme(),
      cardTheme: CardThemeData(
        color: AirwayColors.surface,
        elevation: 0,
        shape: const ContinuousRectangleBorder(
          side: BorderSide(color: AirwayColors.border),
        ),
      ),
      bottomSheetTheme: const BottomSheetThemeData(
        backgroundColor: AirwayColors.surface,
        showDragHandle: true,
        shape: ContinuousRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
        ),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: AirwayColors.surface,
        indicatorColor: AirwayColors.clay.withValues(alpha: 0.18),
        iconTheme: const WidgetStatePropertyAll<IconThemeData?>(
  IconThemeData(color: AirwayColors.textTertiary),
),
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
      ),
      snackBarTheme: const SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        showCloseIcon: true,
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: AirwayColors.surface,
        shape: const ContinuousRectangleBorder(
          borderRadius: BorderRadius.all(Radius.circular(24)),
        ),
      ),
    );
  }
}