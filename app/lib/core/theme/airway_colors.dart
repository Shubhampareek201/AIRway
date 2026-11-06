import 'package:flutter/material.dart';

/// AIRway visual system: clean white canvas, warm wood accents and soft sage.
class AirwayColors {
  AirwayColors._();

  // Brand accents
  static const cream = Color(0xFFF7F3EC);
  static const clay = Color(0xFF987451); // warm wood brown
  static const sage = Color(0xFF66846F); // muted sage green
  static const ink = Color(0xFF29251F);

  static const primary = Color(0xFF315C46);
  static const primarySoft = Color(0xFFEAF1EA);
  static const muted = textTertiary;
  static const textMuted = textSecondary;

  // White app canvas and soft neutral surfaces
  static const surface = Color(0xFFFFFFFF);
  static const surfaceVariant = Color(0xFFF3F7F3);
  static const background = Color(0xFFFFFFFF);
  static const backgroundSolid = Color(0xFFFFFFFF);

  static const text = Color(0xFF29251F);
  static const textSecondary = Color(0xFF77736C);
  static const textTertiary = Color(0xFF9A968E);

  static const border = Color(0xFFEAE6DE);
  static const borderStrong = Color(0xFFD8CCBC);

  // Semantic states
  static const success = Color(0xFF4D8060);
  static const successSoft = Color(0xFFEAF3EC);
  static const warning = Color(0xFFC7793A);
  static const warningSoft = Color(0xFFFFF3E8);
  static const error = Color(0xFFC0392B);
  static const errorSoft = Color(0xFFFFECEA);
  static const info = Color(0xFF4A6FA5);
  static const infoSoft = Color(0xFFEAF0FA);

  // Category accents
  static const beauty = Color(0xFFC47A9A);
  static const beautySoft = Color(0xFFFFEAF2);
  static const gold = Color(0xFFB8863A);

  static const primaryGradient = LinearGradient(
    colors: [Color(0xFF315C46), Color(0xFF66846F)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const heroGradient = LinearGradient(
    colors: [Color(0xFFEAF1EA), Color(0xFFFFFFFF)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const surfaceGradient = LinearGradient(
    colors: [Color(0xFFFFFFFF), Color(0xFFF3F7F3)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );
}
