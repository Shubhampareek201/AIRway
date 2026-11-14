import 'package:flutter/material.dart';

/// AIRway spacing and sizing tokens. Consistent 4px grid.
class AirwaySpacing {
  AirwaySpacing._();

  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 20;
  static const double xxl = 24;
  static const double xxxl = 32;
  static const double huge = 48;

  static const EdgeInsets screenPadding =
      EdgeInsets.symmetric(horizontal: 20, vertical: 16);
  static const EdgeInsets cardPadding =
      EdgeInsets.symmetric(horizontal: 20, vertical: 18);
  static const EdgeInsets sectionPadding =
      EdgeInsets.symmetric(horizontal: 20, vertical: 12);

  static const double cardRadius = 20;
  static const double inputRadius = 16;
  static const double buttonRadius = 16;
  static const double chipRadius = 12;
  static const double avatarRadius = 24;
  static const double imageRadius = 18;

  static const double buttonHeight = 52;
  static const double navigationBarsHeight = 68;
  static const double fabSize = 56;
}