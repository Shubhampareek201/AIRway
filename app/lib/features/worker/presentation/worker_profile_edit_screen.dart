import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:airway/features/worker/data/worker_api.dart';
import 'package:airway/features/worker/data/worker_app_api.dart';
import 'package:airway/features/worker/data/worker_models.dart';

class WorkerProfileEditScreen extends StatefulWidget {
  final WorkerProfile profile;
  const WorkerProfileEditScreen({super.key, required this.profile});

  @override
  State<WorkerProfileEditScreen> createState() => _WorkerProfileEditScreenState();
}

class _WorkerProfileEditScreenState extends State<WorkerProfileEditScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _name;
  late final TextEditingController _experience;
  late final TextEditingController _bio;
  late final TextEditingController _qualification;
  late final TextEditingController _equipment;
  late final TextEditingController _address;
  late final TextEditingController _landmark;
  late final TextEditingController _upi;
  File? _photo;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final p = widget.profile;
    _name = TextEditingController(text: p.name ?? '');
    _experience = TextEditingController(text: (p.experienceYears ?? 0).toString());
    _bio = TextEditingController(text: p.bio ?? '');
    _qualification = TextEditingController(text: p.qualification ?? '');
    _equipment = TextEditingController(text: p.equipmentDetails ?? '');
    _address = TextEditingController(text: p.residentialAddress ?? '');
    _landmark = TextEditingController(text: p.landmark ?? '');
    _upi = TextEditingController(text: p.upiId ?? '');
  }

  @override
  void dispose() {
    for (final c in [_name, _experience, _bio, _qualification, _equipment, _address, _landmark, _upi]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _choosePhoto() async {
    final picked = await ImagePicker().pickImage(source: ImageSource.gallery, imageQuality: 82, maxWidth: 1200);
    if (picked != null && mounted) setState(() => _photo = File(picked.path));
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate() || _saving) return;
    setState(() => _saving = true);
    try {
      await WorkerApi.updateMyProfile({
        'name': _name.text.trim(),
        'experience_years': int.parse(_experience.text.trim()),
        'bio': _bio.text.trim(),
        'qualification': _qualification.text.trim(),
        'equipment_details': _equipment.text.trim(),
        'residential_address': _address.text.trim(),
        'landmark': _landmark.text.trim(),
        'upi_id': _upi.text.trim(),
      });
      if (_photo != null) {
        await WorkerAppApi.uploadIdDocument(docType: 'photo', file: _photo!);
      }
      if (!mounted) return;
      Navigator.pop(context, true);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(_photo == null
            ? 'Profile updated successfully.'
            : 'Profile updated. Your new photo is waiting for admin verification; the current approved photo remains active.'),
        duration: const Duration(seconds: 5),
      ));
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not save profile: $e')));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Widget _field(String label, TextEditingController controller, {int lines = 1, TextInputType? keyboardType, String? Function(String?)? validator}) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: TextFormField(
        controller: controller,
        maxLines: lines,
        keyboardType: keyboardType,
        validator: validator,
        decoration: InputDecoration(labelText: label, alignLabelWithHint: lines > 1),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final image = _photo;
    return Scaffold(
      appBar: AppBar(title: const Text('Edit profile')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(18),
          children: [
            Center(
              child: Column(children: [
                CircleAvatar(
                  radius: 46,
                  backgroundImage: image != null ? FileImage(image) : null,
                  child: image == null ? const Icon(Icons.person, size: 42) : null,
                ),
                TextButton.icon(onPressed: _saving ? null : _choosePhoto, icon: const Icon(Icons.photo_camera_outlined), label: const Text('Change profile photo')),
                if (image != null)
                  const Text('New photo will be visible after admin verification.', textAlign: TextAlign.center, style: TextStyle(fontSize: 12)),
              ]),
            ),
            const SizedBox(height: 18),
            _field('Full name', _name, validator: (v) => v == null || v.trim().isEmpty ? 'Name is required' : null),
            _field('Experience (years)', _experience, keyboardType: TextInputType.number, validator: (v) {
              final n = int.tryParse(v ?? '');
              return n == null || n < 0 || n > 60 ? 'Enter a value from 0 to 60' : null;
            }),
            _field('About your work', _bio, lines: 3),
            _field('Qualification', _qualification),
            _field('Tools / equipment', _equipment, lines: 2),
            _field('Residential address', _address, lines: 2),
            _field('Landmark', _landmark),
            _field('UPI ID for payout', _upi),
            const SizedBox(height: 8),
            FilledButton.icon(
              onPressed: _saving ? null : _save,
              icon: _saving ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.save_outlined),
              label: Text(_saving ? 'Saving…' : 'Save changes'),
            ),
          ],
        ),
      ),
    );
  }
}
