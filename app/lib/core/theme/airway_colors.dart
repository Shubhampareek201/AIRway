import 'package:flutter/material.dart';

/// AIRway design system — color palette.
///
/// AIRway customer palette: clean white surfaces with deep green accents.
class AirwayColors {
  AirwayColors._();

  // === Brand (from logo) ===
  static const cream = Color(0xFFF7F3EC); // warm cream
  static const clay = Color(0xFFA9856A); // warm wood accent
  static const sage = Color(0xFF075B43); // deep green brand accent
  static const ink = Color(0xFF24201C); // wordmark + lines
  // === Compatibility aliases ===
  static const primary = sage;
  static const primarySoft = Color(0xFFE7F2EC);
  static const muted = textTertiary;
  static const textMuted = textSecondary;

  // === Surfaces ===
  static const surface = Color(0xFFFFFFFF);
  static const surfaceVariant = Color(0xFFF2F7F4);
  static const background = Color(0xFFFFFFFF);
  static const backgroundSolid = Color(0xFFF8FAF8);

  static const text = Color(0xFF1E2923);
  static const textSecondary = Color(0xFF748078);
  static const textTertiary = Color(0xFF9AA59E);

  static const border = Color(0xFFE5ECE7);
  static const borderStrong = Color(0xFFC9D8CE);

  // === Semantic ===
  static const success = Color(0xFF2E7D52);
  static const successSoft = Color(0xFFEAF3EC);
  static const warning = Color(0xFFC7793A);
  static const warningSoft = Color(0xFFFFF3E8);
  static const error = Color(0xFFC0392B);
  static const errorSoft = Color(0xFFFFECEA);
  static const info = Color(0xFF4A6FA5);
  static const infoSoft = Color(0xFFEAF0FA);

  // === Accent ===
  static const beauty = Color(0xFFC47A9A);
  static const beautySoft = Color(0xFFFFEAF2);
  static const gold = Color(0xFFB8863A);

  // === Gradients ===
  static const primaryGradient = LinearGradient(
    colors: [Color(0xFF075B43), Color(0xFF2E8A68)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const heroGradient = LinearGradient(
    colors: [Color(0xFFE7F2EC), Color(0xFFFFFFFF)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const surfaceGradient = LinearGradient(
    colors: [Color(0xFFFFFFFF), Color(0xFFF2F7F4)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );
}