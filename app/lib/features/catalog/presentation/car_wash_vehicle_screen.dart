import 'package:flutter/material.dart';
import 'package:airway/features/catalog/data/catalog_api.dart';
import 'package:airway/features/catalog/data/vehicle_models.dart';

class CarWashVehicleScreen extends StatefulWidget {
  final Map<String, List<Map<String, dynamic>>> vehicleTypeSteps;

  const CarWashVehicleScreen({
    super.key,
    this.vehicleTypeSteps = const {},
  });

  @override
  State<CarWashVehicleScreen> createState() => _CarWashVehicleScreenState();
}

class _CarWashVehicleScreenState extends State<CarWashVehicleScreen> {
  static const _green = Color(0xFF315C46);
  static const _ink = Color(0xFF1E2923);
  static const _muted = Color(0xFF748078);
  static const _line = Color(0xFFEAE6DE);

  String? _vehicleType;
  VehicleMake? _make;
  VehicleModel? _model;
  String? _vehicleClass;
  int? _selectedSavedVehicleId;
  List<CustomerVehicle> _savedVehicles = [];
  List<VehicleMake> _makes = [];
  List<VehicleModel> _models = [];
  bool _loadingSaved = true;
  bool _loadingMakes = false;
  bool _loadingModels = false;
  bool _saveAsDefault = false;
  bool _saving = false;
  String _modelSearch = '';
  String _makeSearch = '';
  String? _error;
  int _makeSearchRequest = 0;
  int _modelSearchRequest = 0;

  @override
  void initState() {
    super.initState();
    _loadSavedVehicles();
  }

  Future<void> _loadSavedVehicles() async {
    try {
      final vehicles = await CatalogApi.listSavedVehicles();
      if (!mounted) return;
      setState(() {
        _savedVehicles = [...vehicles]..sort((a, b) => (b.isDefault ? 1 : 0).compareTo(a.isDefault ? 1 : 0));
        _loadingSaved = false;
      });
      final preferred = vehicles.where((v) => v.isDefault).isEmpty
          ? null
          : vehicles.firstWhere((v) => v.isDefault);
      if (preferred != null) _selectSavedVehicle(preferred);
    } catch (_) {
      if (mounted) setState(() => _loadingSaved = false);
    }
  }

  Future<void> _selectType(String type) async {
    setState(() {
      _vehicleType = type;
      _selectedSavedVehicleId = null;
      _make = null;
      _model = null;
      _vehicleClass = null;
      _models = [];
      _makes = [];
      _error = null;
      _loadingMakes = true;
    });
    try {
      final makes = await CatalogApi.listVehicleMakes(type);
      if (!mounted) return;
      setState(() {
        _makes = _prioritisePremiumMakes(makes);
        _loadingMakes = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loadingMakes = false;
        _error = 'Could not load vehicle companies. You can still continue without selecting a model.';
      });
    }
  }

  Future<void> _selectSavedVehicle(CustomerVehicle vehicle) async {
    setState(() {
      _vehicleType = vehicle.vehicleType;
      _selectedSavedVehicleId = vehicle.id;
      _make = null;
      _model = null;
      _vehicleClass = vehicle.vehicleClass.isNotEmpty ? vehicle.vehicleClass : null;
      _models = [];
      _saveAsDefault = vehicle.isDefault;
    });
    final detail = vehicle.modelDetail;
    if (detail != null) {
      setState(() {
        _make = VehicleMake(
          id: detail['make_id'] as int,
          vehicleType: vehicle.vehicleType,
          name: detail['make_name']?.toString() ?? '',
          logo: detail['make_logo']?.toString(),
        );
        _model = VehicleModel(
          id: detail['id'] as int,
          makeId: detail['make_id'] as int,
          makeName: detail['make_name']?.toString() ?? '',
          name: detail['name']?.toString() ?? '',
          image: detail['image']?.toString(),
          vehicleClass: detail['vehicle_class']?.toString() ?? '',
        );
        _vehicleClass = (detail['vehicle_class']?.toString().isNotEmpty == true
            ? detail['vehicle_class']?.toString()
            : vehicle.vehicleClass.isNotEmpty ? vehicle.vehicleClass : null);
      });
      try {
        final makes = await CatalogApi.listVehicleMakes(vehicle.vehicleType);
        if (!mounted) return;
        setState(() { _makes = makes; });
      } catch (_) {
        // Saved vehicle details remain usable even if the make list is unavailable.
      }
      _loadModels(_make!.id, selectedModelId: _model!.id);
    } else {
      setState(() => _loadingMakes = true);
      try {
        final makes = await CatalogApi.listVehicleMakes(vehicle.vehicleType);
        if (!mounted) return;
        setState(() {
          _makes = makes;
          _loadingMakes = false;
        });
      } catch (_) {
        if (mounted) setState(() => _loadingMakes = false);
      }
    }
  }

  Future<void> _loadModels(int makeId, {int? selectedModelId}) async {
    final type = _vehicleType;
    if (type == null) return;
    setState(() {
      _loadingModels = true;
      _models = [];
    });
    try {
      final models = await CatalogApi.listVehicleModels(makeId: makeId, vehicleType: type, vehicleClass: _vehicleClass);
      if (!mounted) return;
      setState(() {
        _models = models;
        _loadingModels = false;
        if (selectedModelId != null) {
          _model = models.where((m) => m.id == selectedModelId).isEmpty
              ? _model
              : models.firstWhere((m) => m.id == selectedModelId);
        }
      });
    } catch (_) {
      if (mounted) setState(() => _loadingModels = false);
    }
  }

  Future<void> _searchMakes(String query) async {
    final type = _vehicleType;
    if (type == null) return;
    final requestId = ++_makeSearchRequest;
    setState(() => _loadingMakes = true);
    try {
      final makes = await CatalogApi.listVehicleMakes(type, search: query);
      if (!mounted || requestId != _makeSearchRequest) return;
      setState(() {
        _makes = makes;
        _loadingMakes = false;
      });
    } catch (_) {
      if (mounted && requestId == _makeSearchRequest) {
        setState(() => _loadingMakes = false);
      }
    }
  }

  Future<void> _searchModels(String query) async {
    final make = _make;
    final type = _vehicleType;
    if (make == null || type == null) return;
    final requestId = ++_modelSearchRequest;
    setState(() => _loadingModels = true);
    try {
      final models = await CatalogApi.listVehicleModels(
        makeId: make.id,
        vehicleType: type,
        vehicleClass: _vehicleClass,
        search: query,
      );
      if (!mounted || requestId != _modelSearchRequest) return;
      setState(() {
        _models = models;
        _loadingModels = false;
      });
    } catch (_) {
      if (mounted && requestId == _modelSearchRequest) {
        setState(() => _loadingModels = false);
      }
    }
  }

  Future<void> _selectVehicleClass(String value) async {
    final type = _vehicleType;
    if (type == null) return;
    setState(() {
      _selectedSavedVehicleId = null;
      _vehicleClass = value;
      _make = null;
      _model = null;
      _models = [];
      _modelSearch = '';
      _loadingMakes = true;
    });
    try {
      final makes = await CatalogApi.listVehicleMakes(type);
      if (!mounted) return;
      setState(() { _makes = _prioritisePremiumMakes(makes); _loadingMakes = false; });
    } catch (_) {
      if (mounted) setState(() { _makes = []; _loadingMakes = false; });
    }
  }

  Future<void> _selectMake(VehicleMake make) async {
    setState(() {
      _selectedSavedVehicleId = null;
      _make = make;
      _model = null;
      _models = [];
      _modelSearch = '';
      _loadingModels = true;
    });
    await _loadModels(make.id);
  }

  Future<void> _continue() async {
    final type = _vehicleType;
    if (type == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please select Car or Bike first.')),
      );
      return;
    }
    if (_vehicleClass == null || _vehicleClass!.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please select your vehicle size/type to see the correct packages.')),
      );
      return;
    }
    if (_saveAsDefault && !_saving) {
      setState(() => _saving = true);
      try {
        if (_selectedSavedVehicleId != null) {
          await CatalogApi.setDefaultVehicle(_selectedSavedVehicleId!);
        } else {
          await CatalogApi.saveVehicle(
            vehicleType: type,
            vehicleModelId: _model?.id,
            customMake: _model == null ? (_make?.name ?? '') : '',
            vehicleClass: _vehicleClass ?? '',
            isDefault: true,
          );
        }
      } catch (e) {
        if (!mounted) return;
        setState(() => _saving = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not save your default vehicle: $e')),
        );
        return;
      }
      if (!mounted) return;
      setState(() => _saving = false);
    }

    final answers = <String, dynamic>{
      'vehicle_kind': type == 'car' ? 'Car' : 'Bike',
      'vehicle_make_id': _make?.id,
      'vehicle_make': _make?.name ?? '',
      'vehicle_model_id': _model?.id,
      'vehicle_model': _model?.name ?? '',
      'vehicle_type': _vehicleClass,
      'vehicle_type_label': _vehicleClass,
    };
    Navigator.pop(context, answers);
  }

  List<Map<String, String>> _vehicleClassOptions() {
    final steps = widget.vehicleTypeSteps[_vehicleType] ?? const [];
    final matchingSteps = steps.where((step) => step['key']?.toString() == 'vehicle_type');
    final options = matchingSteps.isNotEmpty ? matchingSteps.first['options'] : null;
    if (options is List && options.isNotEmpty) {
      final mapped = options.map((item) {
        if (item is Map) {
          final value = item['value']?.toString() ?? item['label']?.toString() ?? '';
          return {'value': value, 'label': item['label']?.toString() ?? value};
        }
        final value = item.toString();
        return {'value': value, 'label': value};
      }).where((item) => item['value']!.isNotEmpty).toList();
      if (_vehicleClass != null &&
          mapped.every((item) => item['value'] != _vehicleClass)) {
        mapped.insert(0, {'value': _vehicleClass!, 'label': _vehicleClass!});
      }
      return mapped;
    }
    final fallback = _vehicleType == 'car'
        ? const ['Hatchback', 'Sedan', 'Compact SUV', 'SUV – 5 Seater', 'SUV – 7 Seater', 'MUV / MPV', 'Luxury Car', 'Luxury SUV']
        : const ['Scooter', 'Motorcycle'];
    return fallback.map((value) => {'value': value, 'label': value}).toList();
  }

  Widget _choice({
    required String title,
    required String subtitle,
    required IconData icon,
    required bool selected,
    required VoidCallback onTap,
  }) {
    return Expanded(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 18, horizontal: 12),
          decoration: BoxDecoration(
            color: selected ? const Color(0xFFEAF1EA) : Colors.white,
            border: Border.all(color: selected ? _green : _line, width: selected ? 2 : 1),
            borderRadius: BorderRadius.circular(16),
          ),
          child: Column(
            children: [
              Icon(icon, size: 34, color: selected ? _green : _muted),
              const SizedBox(height: 8),
              Text(title, style: const TextStyle(fontWeight: FontWeight.w800, color: _ink)),
              Text(subtitle, style: const TextStyle(fontSize: 11, color: _muted)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _sectionTitle(String title, String subtitle) => Padding(
    padding: const EdgeInsets.only(top: 22, bottom: 10),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: _ink)),
        const SizedBox(height: 3),
        Text(subtitle, style: const TextStyle(fontSize: 12, color: _muted)),
      ],
    ),
  );

  // Wikimedia Commons image fallbacks; admin-uploaded catalogue images take priority.
  String? _defaultBrandLogo(String name) {
    final key = name.toLowerCase().replaceAll(RegExp(r'[^a-z]'), '');
    if (key == 'bmw') return 'https://thumb.wikimedia.org/wikipedia/commons/thumb/4/44/BMW.svg/500px-BMW.svg.png';
    if (key == 'audi') return 'https://thumb.wikimedia.org/wikipedia/commons/thumb/1/15/Audi_logo.svg/500px-Audi_logo.svg.png';
    if (key.contains('mercedes')) return 'https://thumb.wikimedia.org/wikipedia/commons/thumb/4/48/Mercedes-Benz_logo.svg/500px-Mercedes-Benz_logo.svg.png';
    if (key.contains('maruti')) return 'https://thumb.wikimedia.org/wikipedia/commons/thumb/8/86/Maruti_Suzuki_logo.svg/500px-Maruti_Suzuki_logo.svg.png';
    if (key.contains('hyundai')) return 'https://thumb.wikimedia.org/wikipedia/commons/thumb/3/33/Hyundai_logo.svg/500px-Hyundai_logo.svg.png';
    if (key.contains('tata')) return 'https://thumb.wikimedia.org/wikipedia/commons/thumb/f/f1/Tata_Motors_Logo.svg/500px-Tata_Motors_Logo.svg.png';
    if (key.contains('honda')) return 'https://thumb.wikimedia.org/wikipedia/commons/thumb/7/7b/Honda_Logo.svg/500px-Honda_Logo.svg.png';
    if (key.contains('toyota')) return 'https://thumb.wikimedia.org/wikipedia/commons/thumb/7/78/Toyota_Logo.svg/500px-Toyota_Logo.svg.png';
    if (key.contains('kia')) return 'https://thumb.wikimedia.org/wikipedia/commons/thumb/2/2f/KIA_logo.svg/500px-KIA_logo.svg.png';
    if (key.contains('mahindra')) return 'https://thumb.wikimedia.org/wikipedia/commons/thumb/d/da/Mahindra_Automotive_new_logo.png/500px-Mahindra_Automotive_new_logo.png';
    if (key.contains('volkswagen') || key == 'vw') return 'https://thumb.wikimedia.org/wikipedia/commons/thumb/2/23/Volkswagen_-_Logo.svg/250px-Volkswagen_-_Logo.svg.png';
    if (key == 'mg' || key.contains('mgmotor')) return 'https://thumb.wikimedia.org/wikipedia/commons/thumb/c/c8/MG_Motor_2021_logo.svg/500px-MG_Motor_2021_logo.svg.png';
    if (key.contains('renault')) return 'https://thumb.wikimedia.org/wikipedia/commons/thumb/3/34/Renault_Logo.svg/500px-Renault_Logo.svg.png';
    if (key.contains('nissan')) return 'https://thumb.wikimedia.org/wikipedia/commons/thumb/2/23/Nissan_2020_logo.svg/500px-Nissan_2020_logo.svg.png';
    if (key.contains('skoda')) return 'https://thumb.wikimedia.org/wikipedia/commons/thumb/a/a5/Skoda_Logo.png/330px-Skoda_Logo.png';
    if (key.contains('jeep')) return 'https://commons.wikimedia.org/wiki/Special:FilePath/Jeep_logo.svg';
    if (key.contains('citroen')) return 'https://commons.wikimedia.org/wiki/Special:FilePath/Citroën_2022.svg';
    if (key.contains('byd')) return 'https://commons.wikimedia.org/wiki/Special:FilePath/BYD_Auto_logo.svg';
    if (key.contains('volvo')) return 'https://commons.wikimedia.org/wiki/Special:FilePath/Volvo_Iron_Mark.svg';
    if (key.contains('isuzu')) return 'https://commons.wikimedia.org/wiki/Special:FilePath/Isuzu_logo.svg';
    if (key.contains('force')) return 'https://commons.wikimedia.org/wiki/Special:FilePath/Force_Motors_logo.svg';
    if (key == 'mini') return 'https://commons.wikimedia.org/wiki/Special:FilePath/Mini_logo.svg';
    return null;
  }

  String? _defaultModelImage(String name) {
    final key = name.toLowerCase().trim();
    if (key == 'swift') return 'https://thumb.wikimedia.org/wikipedia/commons/thumb/e/eb/Swift.jpg/330px-Swift.jpg';
    if (key == 'creta') return 'https://thumb.wikimedia.org/wikipedia/commons/thumb/3/3d/Hyundai_Creta_1.5_Plus_2024.jpg/640px-Hyundai_Creta_1.5_Plus_2024.jpg';
    if (key == 'city') return 'https://thumb.wikimedia.org/wikipedia/commons/thumb/1/1f/0_Honda_City_%287th_generation%29_sedan.jpg/640px-0_Honda_City_%287th_generation%29_sedan.jpg';
    if (key == 'innova crysta' || key == 'innova') return 'https://thumb.wikimedia.org/wikipedia/commons/thumb/6/68/Toyota_Innova_Crysta.jpg/640px-Toyota_Innova_Crysta.jpg';
    if (key == 'safari') return 'https://thumb.wikimedia.org/wikipedia/commons/thumb/1/15/Tata_Safari.jpg/640px-Tata_Safari.jpg';
    if (key == 'fortuner') return 'https://thumb.wikimedia.org/wikipedia/commons/thumb/d/dc/Toyota_Fortuner_4x2_Legender_2023_%287%29.jpg/640px-Toyota_Fortuner_4x2_Legender_2023_%287%29.jpg';
    return null;
  }

  // Black front-right three-quarter studio references on white backgrounds.
  // These are body-style illustrations; exact model photographs come from the database.
  String? _bodyTypeImage(String value) {
    final key = value.toLowerCase();
    if (key.contains('hatch')) {
      return 'https://www.2dvornika.com.ua/public/images/cars/seatibiza5.jpg';
    }
    if (key.contains('sedan') || key.contains('luxury car')) {
      return 'https://s1.auto.drom.ru/photo/9Ch2Z4zgM4nUJ7_8WC6-yC6vcmEBsqSB9XpYsxoXo8V0Y6RxlunS7QpbMzZMpdbjvDgbG-O_dDy2CEfdaRTRaLYfLgreHD_5OS60DuLsnaG0yK6hq7E.jpg';
    }
    if (key.contains('muv') || key.contains('mpv')) {
      return 'https://i5.walmartimages.cl/asr/e9299c31-2334-493a-8209-c897ecdd4238.7804224ef938eacc5a547ca9f7aac02b.png?odnBg=ffffff&odnHeight=2000&odnWidth=2000';
    }
    if (key.contains('suv') || key.contains('luxury') || key.contains('7')) {
      return 'https://images.91wheels.com/assets/uploads/swatchs/XUV700_EbonyBlack1742199441.jpg?q=40&w=1040';
    }
    return null;
  }

  List<VehicleMake> _prioritisePremiumMakes(List<VehicleMake> makes) {
    const priority = ['bmw', 'audi', 'mercedes'];
    final sorted = [...makes];
    sorted.sort((a, b) {
      int rank(String name) {
        final index = priority.indexWhere((brand) => name.toLowerCase().contains(brand));
        return index < 0 ? priority.length : index;
      }
      return rank(a.name).compareTo(rank(b.name));
    });
    return sorted;
  }

  Widget _makeTile(VehicleMake make) {
    final selected = _make?.id == make.id;
    final fallback = _defaultBrandLogo(make.name);
    final logo = (make.logo != null && make.logo!.isNotEmpty) ? make.logo! : fallback;
    return InkWell(
      onTap: () => _selectMake(make),
      borderRadius: BorderRadius.circular(13),
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: Colors.white,
          border: Border.all(color: selected ? _green : _line, width: selected ? 2 : 1),
          borderRadius: BorderRadius.circular(13),
        ),
        child: Center(
          child: logo == null
              ? const Icon(Icons.directions_car_filled_outlined, size: 34, color: Color(0xFF68736B))
              : Image.network(
                  logo,
                  fit: BoxFit.contain,
                  errorBuilder: (_, __, ___) => const Icon(
                    Icons.directions_car_filled_outlined,
                    size: 34,
                    color: Color(0xFF68736B),
                  ),
                ),
        ),
      ),
    );
  }

  Widget _modelTile(VehicleModel model) {
    final selected = _model?.id == model.id;
    return InkWell(
      onTap: () => setState(() { _selectedSavedVehicleId = null; _model = model; _vehicleClass = model.vehicleClass.isNotEmpty ? model.vehicleClass : null; }),
      borderRadius: BorderRadius.circular(14),
      child: Container(
        decoration: BoxDecoration(
          color: selected ? const Color(0xFFEAF1EA) : Colors.white,
          border: Border.all(color: selected ? _green : _line, width: selected ? 2 : 1),
          borderRadius: BorderRadius.circular(14),
        ),
        clipBehavior: Clip.antiAlias,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(
              child: (model.image ?? _defaultModelImage(model.name)) == null
                ? const ColoredBox(color: Color(0xFFF4F5F2), child: Icon(Icons.directions_car_filled_outlined, size: 42, color: _muted))
                : Image.network(model.image ?? _defaultModelImage(model.name)!, fit: BoxFit.contain,
                    errorBuilder: (_, __, ___) => const ColoredBox(color: Color(0xFFF4F5F2), child: Icon(Icons.directions_car_filled_outlined, size: 42, color: _muted))),
            ),
            Padding(
              padding: const EdgeInsets.all(8),
              child: Row(children: [
                Expanded(child: Text(model.name, maxLines: 2, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: _ink))),
                if (selected) const Icon(Icons.check_circle, size: 17, color: _green),
              ]),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFAFAF8),
      appBar: AppBar(title: const Text('Your vehicle'), backgroundColor: Colors.white),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(18, 16, 18, 24),
        children: [
          const Text('Which vehicle needs cleaning?', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w900, color: _ink)),
          const SizedBox(height: 6),
          const Text('Choose the vehicle type. Company and model details are optional.', style: TextStyle(color: _muted, fontSize: 13)),
          if (_loadingSaved) const LinearProgressIndicator(minHeight: 2),
          if (_savedVehicles.isNotEmpty) ...[
            _sectionTitle('Your saved vehicles', 'Select a saved vehicle to use it again.'),
            ..._savedVehicles.map((vehicle) => Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: ListTile(
                tileColor: Colors.white,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(13), side: const BorderSide(color: _line)),
                leading: Icon(vehicle.vehicleType == 'car' ? Icons.directions_car : Icons.two_wheeler, color: _green),
                title: Text(vehicle.displayName.isEmpty ? (vehicle.vehicleType == 'car' ? 'Car' : 'Bike') : vehicle.displayName,
                  style: const TextStyle(fontWeight: FontWeight.w700)),
                subtitle: Text(vehicle.isDefault ? 'Default vehicle' : vehicle.vehicleType.toUpperCase()),
                trailing: vehicle.isDefault ? const Icon(Icons.check_circle, color: _green) : null,
                onTap: () => _selectSavedVehicle(vehicle),
              ),
            )),
          ],
          const SizedBox(height: 16),
          Row(children: [
            _choice(title: 'Car', subtitle: 'Four-wheeler', icon: Icons.directions_car_filled, selected: _vehicleType == 'car', onTap: () => _selectType('car')),
            const SizedBox(width: 12),
            _choice(title: 'Bike', subtitle: 'Two-wheeler', icon: Icons.two_wheeler, selected: _vehicleType == 'bike', onTap: () => _selectType('bike')),
          ]),
          if (_vehicleType != null) ...[
            _sectionTitle(
              _vehicleType == 'car' ? 'Choose your car body type' : 'Choose your two-wheeler type',
              'Select the closest match. This is enough to show the right starting price.',
            ),
            SizedBox(
              height: 148,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: _vehicleClassOptions().length,
                separatorBuilder: (_, __) => const SizedBox(width: 10),
                itemBuilder: (_, index) {
                  final option = _vehicleClassOptions()[index];
                  final value = option['value']!;
                  final selected = _vehicleClass == value;
                  final bodyImage = _vehicleType == 'car' ? _bodyTypeImage(value) : null;
                  return InkWell(
                    onTap: () => _selectVehicleClass(value),
                    borderRadius: BorderRadius.circular(14),
                    child: Container(
                      width: 132,
                      padding: const EdgeInsets.all(9),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        border: Border.all(color: selected ? _green : _line, width: selected ? 2 : 1),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: Column(
                        children: [
                          Expanded(
                            child: ColoredBox(
                              color: Colors.white,
                              child: bodyImage == null
                                  ? CustomPaint(painter: _VehicleBodyPainter(value, selected), child: const SizedBox.expand())
                                  : Image.network(
                                      bodyImage,
                                      fit: BoxFit.contain,
                                      errorBuilder: (_, __, ___) => const SizedBox.expand(),
                                    ),
                            ),
                          ),
                          const SizedBox(height: 6),
                          Text(option['label']!, textAlign: TextAlign.center, maxLines: 2,
                            style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: _ink)),
                        ],
                      ),
                    ),
                  );
                },
              ),
            ),
            if (_vehicleClass != null) ...[
              _sectionTitle('Choose your car company (optional)', 'Browse all available brands. Select one to see its models below.'),
              TextField(
                onChanged: (value) { setState(() => _makeSearch = value); _searchMakes(value); },
                decoration: InputDecoration(
                  hintText: 'Search car company',
                  prefixIcon: const Icon(Icons.search),
                  filled: true, fillColor: Colors.white,
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(13)),
                ),
              ),
              const SizedBox(height: 10),
              if (_loadingMakes) const Center(child: Padding(padding: EdgeInsets.all(12), child: CircularProgressIndicator())),
              if (!_loadingMakes && _makes.isEmpty)
                const Text('No manufacturers are configured yet. You can continue without selecting one.', style: TextStyle(color: _muted, fontSize: 12)),
              if (_makes.isNotEmpty) ...[
                Builder(builder: (context) {
                  final visibleMakes = _makeSearch.trim().isEmpty ? _makes.take(6).toList() : _makes;
                  return GridView.builder(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    itemCount: visibleMakes.length,
                    gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                      crossAxisCount: 3, mainAxisSpacing: 9, crossAxisSpacing: 9, childAspectRatio: 1.05,
                    ),
                    itemBuilder: (_, index) => _makeTile(visibleMakes[index]),
                  );
                }),
                if (_makeSearch.trim().isEmpty && _makes.length > 6)
                  const Padding(
                    padding: EdgeInsets.only(top: 4),
                    child: Text('Search to find any other available company.', style: TextStyle(color: _muted, fontSize: 11)),
                  ),
              ],
              if (_make != null) ...[
                _sectionTitle('Find your model (optional)', 'Search and choose your exact model to refine pricing.'),
                TextField(
                  onChanged: (value) { setState(() => _modelSearch = value); _searchModels(value); },
                  decoration: InputDecoration(
                    hintText: 'Search model name',
                    prefixIcon: const Icon(Icons.search),
                    filled: true, fillColor: Colors.white,
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(13)),
                  ),
                ),
                if (_loadingModels) const Center(child: Padding(padding: EdgeInsets.all(12), child: CircularProgressIndicator())),
                if (!_loadingModels && _models.isEmpty)
                  const Text('No models are configured for this company and vehicle type.', style: TextStyle(color: _muted, fontSize: 12)),
                if (_models.isNotEmpty)
                  SizedBox(
                    height: 190,
                    child: GridView.builder(
                      scrollDirection: Axis.horizontal,
                      itemCount: _modelSearch.trim().isEmpty
                          ? (_models.length < 4 ? _models.length : 4)
                          : _models.length,
                      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                        crossAxisCount: 1, mainAxisExtent: 145, mainAxisSpacing: 10,
                      ),
                      itemBuilder: (_, index) => _modelTile(_models[index]),
                    ),
                  ),
                if (_modelSearch.trim().isEmpty && _models.length > 4)
                  const Padding(
                    padding: EdgeInsets.only(top: 4),
                    child: Text('Search to find any other model from this company.', style: TextStyle(color: _muted, fontSize: 11)),
                  ),
              ],
            ],
            const SizedBox(height: 12),
            CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              value: _saveAsDefault,
              activeColor: _green,
              onChanged: (value) => setState(() => _saveAsDefault = value ?? false),
              title: const Text('Save this as my default vehicle', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
              subtitle: const Text('You can change it anytime.', style: TextStyle(fontSize: 11)),
            ),
          ],
          if (_error != null) Padding(padding: const EdgeInsets.only(top: 8), child: Text(_error!, style: const TextStyle(color: Colors.red, fontSize: 12))),
          const SizedBox(height: 14),
          FilledButton(
            onPressed: _vehicleType == null || _saving ? null : _continue,
            style: FilledButton.styleFrom(backgroundColor: _green, padding: const EdgeInsets.symmetric(vertical: 16)),
            child: Text(_saving ? 'Saving...' : 'Continue to services'),
          ),
          TextButton(
            onPressed: _vehicleType == null ? null : () {
              setState(() { _selectedSavedVehicleId = null; _make = null; _model = null; });
              _continue();
            },
            child: const Text('Skip company and model'),
          ),
        ],
      ),
    );
  }
}


class _VehicleBodyPainter extends CustomPainter {
  final String bodyType;
  final bool selected;
  const _VehicleBodyPainter(this.bodyType, this.selected);

  @override
  void paint(Canvas canvas, Size size) {
    final fill = Paint()..color = selected ? const Color(0xFF315C46) : const Color(0xFF89968D);
    final glass = Paint()..color = const Color(0xFFEAF0EC);
    final wheel = Paint()..color = const Color(0xFF34413A);
    final w = size.width;
    final h = size.height;
    final kind = bodyType.toLowerCase();
    double roofStart = 0.30, roofEnd = 0.68, roofHeight = 0.30;
    if (kind.contains('sedan')) { roofStart = 0.28; roofEnd = 0.68; roofHeight = 0.29; }
    if (kind.contains('hatch')) { roofStart = 0.34; roofEnd = 0.70; roofHeight = 0.27; }
    if (kind.contains('compact')) { roofStart = 0.29; roofEnd = 0.70; roofHeight = 0.23; }
    if (kind.contains('suv') || kind.contains('luxury')) { roofStart = 0.25; roofEnd = 0.72; roofHeight = 0.19; }
    if (kind.contains('muv') || kind.contains('mpv') || kind.contains('7')) { roofStart = 0.20; roofEnd = 0.78; roofHeight = 0.18; }
    final baseY = h * 0.72;
    final roofY = h * roofHeight;
    final path = Path()
      ..moveTo(w * 0.08, baseY)
      ..lineTo(w * 0.14, h * 0.54)
      ..quadraticBezierTo(w * 0.18, h * 0.49, w * roofStart, roofY + h * 0.12)
      ..quadraticBezierTo(w * 0.43, roofY, w * roofEnd, roofY + h * 0.12)
      ..lineTo(w * 0.86, h * 0.53)
      ..lineTo(w * 0.94, h * 0.59)
      ..lineTo(w * 0.96, baseY)
      ..close();
    canvas.drawPath(path, fill);
    final windowPath = Path()
      ..moveTo(w * (roofStart + 0.035), roofY + h * 0.15)
      ..lineTo(w * (roofEnd - 0.025), roofY + h * 0.15)
      ..lineTo(w * 0.79, h * 0.53)
      ..lineTo(w * 0.20, h * 0.53)
      ..close();
    canvas.drawPath(windowPath, glass);
    canvas.drawCircle(Offset(w * 0.28, baseY), h * 0.13, wheel);
    canvas.drawCircle(Offset(w * 0.75, baseY), h * 0.13, wheel);
    final hub = Paint()..color = const Color(0xFFDDE3DE);
    canvas.drawCircle(Offset(w * 0.28, baseY), h * 0.055, hub);
    canvas.drawCircle(Offset(w * 0.75, baseY), h * 0.055, hub);
  }

  @override
  bool shouldRepaint(covariant _VehicleBodyPainter oldDelegate) =>
      oldDelegate.bodyType != bodyType || oldDelegate.selected != selected;
}
