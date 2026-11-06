import 'package:flutter/material.dart';

/// AIRway design system — color palette.
///
/// Derived directly from the AIRway logo mark:
///   - warm cream ground   #F3EFAE
///   - clay / terracotta   #A9856A
///   - sage green          #7C8A6E
///   - dark ink            #24201C
/// A single warm, earthy identity shared by the customer and worker apps.
class AirwayColors {
  AirwayColors._();

  // === Brand (from logo) ===
  static const cream = Color(0xFFF7F3EC); // warm cream
  static const clay = Color(0xFFA9856A); // warm wood accent
  static const sage = Color(0xFF7861A8); // violet brand
  static const ink = Color(0xFF24201C); // wordmark + lines
    // === Compatibility aliases ===
  static const primary = sage;
  static const primarySoft = Color(0xFFEDE7F5);
  static const muted = textTertiary;
  static const textMuted = textSecondary;

  // === Surfaces ===
  static const surface = Color(0xFFFFFFFF);
  static const surfaceVariant = Color(0xFFF1EBF7);
  static const background = Color(0xFFF7F3EC);
  static const backgroundSolid = Color(0xFFFBF8F3);

  static const text = Color(0xFF24201C);
  static const textSecondary = Color(0xFF6B655C);
  static const textTertiary = Color(0xFF9B9588);

  static const border = Color(0xFFE8E0ED);
  static const borderStrong = Color(0xFFD8CBE2);

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
    colors: [Color(0xFF7861A8), Color(0xFFA9856A)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const heroGradient = LinearGradient(
    colors: [Color(0xFFF1EAF7), Color(0xFFF7F3EC)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const surfaceGradient = LinearGradient(
    colors: [Color(0xFFFBF8F3), Color(0xFFF4F1EA)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );
}