import 'package:airway/core/network/auth_api.dart';

class VehicleMake {
  final int id;
  final String vehicleType;
  final String name;
  final String? logo;
  const VehicleMake({required this.id, required this.vehicleType, required this.name, this.logo});

  factory VehicleMake.fromMap(Map<String, dynamic> map) => VehicleMake(
    id: map['id'] as int,
    vehicleType: map['vehicle_type']?.toString() ?? '',
    name: map['name']?.toString() ?? '',
    logo: _vehicleMedia(map['logo']),
  );
}

class VehicleModel {
  final int id;
  final int makeId;
  final String makeName;
  final String name;
  final String? image;
  final String vehicleClass;
  const VehicleModel({
    required this.id, required this.makeId, required this.makeName,
    required this.name, this.image, this.vehicleClass = '',
  });

  factory VehicleModel.fromMap(Map<String, dynamic> map) => VehicleModel(
    id: map['id'] as int,
    makeId: map['make'] as int,
    makeName: map['make_name']?.toString() ?? '',
    name: map['name']?.toString() ?? '',
    image: _vehicleMedia(map['image']),
    vehicleClass: map['vehicle_class']?.toString() ?? '',
  );
}

class CustomerVehicle {
  final int id;
  final String vehicleType;
  final int? vehicleModelId;
  final String customMake;
  final String customModel;
  final String nickname;
  final bool isDefault;
  final Map<String, dynamic>? modelDetail;

  const CustomerVehicle({
    required this.id, required this.vehicleType, this.vehicleModelId,
    this.customMake = '', this.customModel = '', this.nickname = '',
    this.isDefault = false, this.modelDetail,
  });

  factory CustomerVehicle.fromMap(Map<String, dynamic> map) => CustomerVehicle(
    id: map['id'] as int,
    vehicleType: map['vehicle_type']?.toString() ?? '',
    vehicleModelId: map['vehicle_model'] as int?,
    customMake: map['custom_make']?.toString() ?? '',
    customModel: map['custom_model']?.toString() ?? '',
    nickname: map['nickname']?.toString() ?? '',
    isDefault: map['is_default'] == true,
    modelDetail: map['vehicle_model_detail'] is Map
      ? Map<String, dynamic>.from(map['vehicle_model_detail'] as Map)
      : null,
  );

  String get displayName {
    final detail = modelDetail;
    if (detail != null) return '${detail['make_name'] ?? ''} ${detail['name'] ?? ''}'.trim();
    return [customMake, customModel].where((v) => v.isNotEmpty).join(' ');
  }
}

String? _vehicleMedia(dynamic value) {
  final raw = value?.toString().trim() ?? '';
  if (raw.isEmpty) return null;
  final uri = Uri.tryParse(raw);
  if (uri == null) return null;
  final base = Uri.parse(AuthApi.baseUrl);
  if (!uri.hasScheme || uri.host.isEmpty) return base.resolve(raw).toString();
  if ({'localhost', '127.0.0.1', '0.0.0.0'}.contains(uri.host) &&
      !{'localhost', '127.0.0.1', '0.0.0.0'}.contains(base.host)) {
    return uri.replace(scheme: base.scheme, host: base.host, port: base.hasPort ? base.port : null).toString();
  }
  return uri.toString();
}
