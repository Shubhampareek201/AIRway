import 'package:airway/core/localization/airway_locale.dart';


class AirwayText {
  AirwayText._();

  static String tr(String english, String hindi) =>
      AirwayLocale.current.languageCode == 'hi' ? hindi : english;
}
