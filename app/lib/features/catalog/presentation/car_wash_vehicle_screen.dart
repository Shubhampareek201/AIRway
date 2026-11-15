import 'package:flutter/material.dart';
import 'package:airway/features/catalog/data/catalog_api.dart';
import 'package:airway/features/catalog/data/vehicle_models.dart';

class CarWashVehicleScreen extends StatefulWidget {
  const CarWashVehicleScreen({super.key});

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
  List<CustomerVehicle> _savedVehicles = [];
  List<VehicleMake> _makes = [];
  List<VehicleModel> _models = [];
  bool _loadingSaved = true;
  bool _loadingMakes = false;
  bool _loadingModels = false;
  bool _saveAsDefault = false;
  bool _saving = false;
  String? _error;

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
        _savedVehicles = vehicles;
        _loadingSaved = false;
      });
      final preferred = vehicles.where((v) => v.isDefault).firstOrNull;
      if (preferred != null) _selectSavedVehicle(preferred);
    } catch (_) {
      if (mounted) setState(() => _loadingSaved = false);
    }
  }

  Future<void> _selectType(String type) async {
    setState(() {
      _vehicleType = type;
      _make = null;
      _model = null;
      _models = [];
      _makes = [];
      _error = null;
      _loadingMakes = true;
    });
    try {
      final makes = await CatalogApi.listVehicleMakes(type);
      if (!mounted) return;
      setState(() {
        _makes = makes;
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

  void _selectSavedVehicle(CustomerVehicle vehicle) {
    setState(() {
      _vehicleType = vehicle.vehicleType;
      _make = null;
      _model = null;
      _models = [];
      _saveAsDefault = true;
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
      });
      _loadModels(_make!.id, selectedModelId: _model!.id);
    } else {
      _selectType(vehicle.vehicleType);
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
      final models = await CatalogApi.listVehicleModels(makeId: makeId, vehicleType: type);
      if (!mounted) return;
      setState(() {
        _models = models;
        _loadingModels = false;
        if (selectedModelId != null) {
          _model = models.where((m) => m.id == selectedModelId).firstOrNull ?? _model;
        }
      });
    } catch (_) {
      if (mounted) setState(() => _loadingModels = false);
    }
  }

  Future<void> _selectMake(VehicleMake make) async {
    setState(() {
      _make = make;
      _model = null;
      _models = [];
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
    if (_saveAsDefault && !_saving) {
      setState(() => _saving = true);
      try {
        await CatalogApi.saveVehicle(
          vehicleType: type,
          vehicleModelId: _model?.id,
          customMake: _model == null ? (_make?.name ?? '') : '',
          isDefault: true,
        );
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
    };
    if (_model?.vehicleClass.isNotEmpty == true) {
      answers['vehicle_type'] = _model!.vehicleClass;
      answers['vehicle_type_label'] = _model!.vehicleClass;
    }
    Navigator.pop(context, answers);
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

  Widget _makeTile(VehicleMake make) {
    final selected = _make?.id == make.id;
    return InkWell(
      onTap: () => _selectMake(make),
      borderRadius: BorderRadius.circular(13),
      child: Container(
        width: 104,
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: selected ? const Color(0xFFEAF1EA) : Colors.white,
          border: Border.all(color: selected ? _green : _line, width: selected ? 2 : 1),
          borderRadius: BorderRadius.circular(13),
        ),
        child: Column(
          children: [
            SizedBox(
              height: 44,
              child: make.logo == null
                ? const Icon(Icons.directions_car_filled_outlined, color: _muted, size: 32)
                : Image.network(make.logo!, fit: BoxFit.contain,
                    errorBuilder: (_, __, ___) => const Icon(Icons.directions_car_filled_outlined, color: _muted, size: 32)),
            ),
            const SizedBox(height: 6),
            Text(make.name, maxLines: 2, textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: _ink)),
          ],
        ),
      ),
    );
  }

  Widget _modelTile(VehicleModel model) {
    final selected = _model?.id == model.id;
    return InkWell(
      onTap: () => setState(() => _model = model),
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
              child: model.image == null
                ? const ColoredBox(color: Color(0xFFF4F5F2), child: Icon(Icons.directions_car_filled_outlined, size: 42, color: _muted))
                : Image.network(model.image!, fit: BoxFit.contain,
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
            _sectionTitle('Select company (optional)', 'Choose your vehicle manufacturer.'),
            if (_loadingMakes) const Center(child: Padding(padding: EdgeInsets.all(12), child: CircularProgressIndicator())),
            if (!_loadingMakes && _makes.isEmpty)
              const Text('No manufacturers are configured yet. You can continue without selecting one.', style: TextStyle(color: _muted, fontSize: 12)),
            if (_makes.isNotEmpty)
              SizedBox(height: 112, child: ListView.separated(
                scrollDirection: Axis.horizontal, itemCount: _makes.length,
                separatorBuilder: (_, __) => const SizedBox(width: 9),
                itemBuilder: (_, index) => _makeTile(_makes[index]),
              )),
            if (_make != null) ...[
              _sectionTitle('Select model (optional)', 'Choose your exact model if it is listed.'),
              if (_loadingModels) const Center(child: Padding(padding: EdgeInsets.all(12), child: CircularProgressIndicator())),
              if (!_loadingModels && _models.isEmpty)
                const Text('No models are configured for this company yet.', style: TextStyle(color: _muted, fontSize: 12)),
              if (_models.isNotEmpty)
                SizedBox(
                  height: 190,
                  child: GridView.builder(
                    scrollDirection: Axis.horizontal,
                    itemCount: _models.length,
                    gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                      crossAxisCount: 1, mainAxisExtent: 145, mainAxisSpacing: 10,
                    ),
                    itemBuilder: (_, index) => _modelTile(_models[index]),
                  ),
                ),
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
              setState(() { _make = null; _model = null; });
              _continue();
            },
            child: const Text('Skip company and model'),
          ),
        ],
      ),
    );
  }
}
