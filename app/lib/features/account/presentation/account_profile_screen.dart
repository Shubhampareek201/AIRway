import 'dart:io';
import 'package:airway/core/localization/airway_text.dart';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/account/data/account_api.dart';

class AccountProfileScreen extends StatefulWidget {
  final bool workerMode;

  const AccountProfileScreen({super.key, this.workerMode = false});

  @override
  State<AccountProfileScreen> createState() => _AccountProfileScreenState();
}

class _AccountProfileScreenState extends State<AccountProfileScreen> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _email = TextEditingController();
  Map<String, dynamic>? _profile;
  File? _photo;
  String? _gender;
  bool _loading = true;
  bool _saving = false;
  String? _error;

  static const _genders = <String, String>{
    'male': 'Male',
    'female': 'Female',
    'other': 'Other',
    'prefer_not_to_say': 'Prefer not to say',
  };

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final profile = await AccountApi.fetchProfile();
      if (!mounted) return;
      setState(() {
        _profile = profile;
        _name.text = profile['name']?.toString() ?? '';
        _email.text = profile['email']?.toString() ?? '';
        final gender = profile['gender']?.toString();
        _gender = _genders.containsKey(gender) ? gender : null;
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.toString().replaceFirst('Exception: ', '');
        _loading = false;
      });
    }
  }

  Future<void> _choosePhoto() async {
    final source = await showModalBottomSheet<ImageSource>(
      context: context,
      builder: (sheetContext) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.camera_alt_outlined),
              title: Text(AirwayText.tr('Take a photo', 'फ़ोटो लें')),
              onTap: () => Navigator.pop(sheetContext, ImageSource.camera),
            ),
            ListTile(
              leading: const Icon(Icons.photo_library_outlined),
              title: Text(AirwayText.tr('Choose from gallery', 'गैलरी से चुनें')),
              onTap: () => Navigator.pop(sheetContext, ImageSource.gallery),
            ),
          ],
        ),
      ),
    );
    if (source == null || !mounted) return;
    try {
      final picked = await ImagePicker().pickImage(
        source: source,
        imageQuality: 82,
        maxWidth: 1200,
        maxHeight: 1200,
      );
      if (picked == null || !mounted) return;
      final file = File(picked.path);
      if (await file.length() > 5 * 1024 * 1024) {
        _message(AirwayText.tr('Choose an image smaller than 5 MB.', '5 MB से छोटी इमेज चुनें।'));
        return;
      }
      setState(() => _photo = file);
    } catch (_) {
      _message(AirwayText.tr('Could not open the photo gallery. Please try again.', 'फ़ोटो गैलरी नहीं खुल सकी। फिर से कोशिश करें।'));
    }
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate() || _saving) return;
    setState(() => _saving = true);
    try {
      await AccountApi.updateProfile(
        data: {
          'name': _name.text.trim(),
          'email': _email.text.trim(),
          if (_gender != null) 'gender': _gender,
        },
        photo: _photo,
      );
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } catch (error) {
      if (!mounted) return;
      _message(error.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  void _message(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  Widget _avatar() {
    final photo = _photo;
    final workerProfile = _profile?['worker_profile'];
    final photoUrl = widget.workerMode && workerProfile is Map
        ? workerProfile['photo_url']?.toString()
        : _profile?['photo_url']?.toString();
    Widget image;
    if (photo != null) {
      image = Image.file(photo, width: 104, height: 104, fit: BoxFit.cover);
    } else if (photoUrl != null && photoUrl.isNotEmpty) {
      image = Image.network(
        photoUrl,
        width: 104,
        height: 104,
        fit: BoxFit.cover,
        errorBuilder: (_, __, ___) => _avatarFallback(),
      );
    } else {
      image = _avatarFallback();
    }
    return ClipOval(child: SizedBox(width: 104, height: 104, child: image));
  }

  Widget _avatarFallback() => Container(
    color: AirwayColors.primary.withValues(alpha: 0.12),
    alignment: Alignment.center,
    child: const Icon(Icons.person_rounded, size: 48, color: AirwayColors.primary),
  );

  @override
  Widget build(BuildContext context) {
    final phone = _profile?['phone']?.toString() ?? 'Not available';
    return Scaffold(
      appBar: AppBar(title: Text(AirwayText.tr('Personal information', 'व्यक्तिगत जानकारी'))),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.cloud_off_outlined, size: 42),
                        const SizedBox(height: 12),
                        Text(_error!, textAlign: TextAlign.center),
                        const SizedBox(height: 16),
                        FilledButton.icon(
                          onPressed: _load,
                          icon: const Icon(Icons.refresh_rounded),
                          label: Text(AirwayText.tr('Retry', 'फिर कोशिश करें')),
                        ),
                      ],
                    ),
                  ),
                )
              : Form(
                  key: _formKey,
                  child: ListView(
                    padding: const EdgeInsets.all(20),
                    children: [
                      Center(
                        child: Column(
                          children: [
                            _avatar(),
                            const SizedBox(height: 8),
                            if (!widget.workerMode)
                              TextButton.icon(
                                onPressed: _saving ? null : _choosePhoto,
                                icon: const Icon(Icons.camera_alt_outlined),
                                label: Text(AirwayText.tr('Change profile photo', 'प्रोफ़ाइल फ़ोटो बदलें')),
                              )
                            else
                              const Text(
                                'Worker profile photos are updated from Work profile details and require verification.',
                                textAlign: TextAlign.center,
                                style: TextStyle(fontSize: 12, color: AirwayColors.textSecondary),
                              ),
                            if (_photo != null)
                              Text(AirwayText.tr('New photo selected', 'नई फ़ोटो चुनी गई'), style: TextStyle(fontSize: 12, color: AirwayColors.textSecondary)),
                          ],
                        ),
                      ),
                      const SizedBox(height: 20),
                      TextFormField(
                        controller: _name,
                        textCapitalization: TextCapitalization.words,
                        textInputAction: TextInputAction.next,
                        decoration: const InputDecoration(
                          labelText: AirwayText.tr('Full name', 'पूरा नाम'),
                          prefixIcon: Icon(Icons.person_outline_rounded),
                        ),
                        validator: (value) => value == null || value.trim().isEmpty
                            ? 'Please enter your name.'
                            : value.trim().length > 150
                                ? 'Name must be 150 characters or fewer.'
                                : null,
                      ),
                      const SizedBox(height: 14),
                      TextFormField(
                        controller: _email,
                        keyboardType: TextInputType.emailAddress,
                        textInputAction: TextInputAction.next,
                        decoration: const InputDecoration(
                          labelText: AirwayText.tr('Email address (optional)', 'ईमेल पता (वैकल्पिक)'),
                          prefixIcon: Icon(Icons.email_outlined),
                        ),
                        validator: (value) {
                          final email = value?.trim() ?? '';
                          if (email.isEmpty) return null;
                          return RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$').hasMatch(email)
                              ? null
                              : 'Enter a valid email address.';
                        },
                      ),
                      const SizedBox(height: 14),
                      DropdownButtonFormField<String>(
                        initialValue: _gender,
                        decoration: const InputDecoration(
                          labelText: AirwayText.tr('Gender (optional)', 'लिंग (वैकल्पिक)'),
                          prefixIcon: Icon(Icons.person_pin_outlined),
                        ),
                        items: _genders.entries
                            .map((entry) => DropdownMenuItem(
                                  value: entry.key,
                                  child: Text(entry.value),
                                ))
                            .toList(),
                        onChanged: _saving ? null : (value) => setState(() => _gender = value),
                      ),
                      const SizedBox(height: 14),
                      InputDecorator(
                        decoration: const InputDecoration(
                          labelText: AirwayText.tr('Registered phone number', 'रजिस्टर्ड फ़ोन नंबर'),
                          prefixIcon: Icon(Icons.phone_android_rounded),
                          helperText: 'Phone changes require OTP re-verification.',
                        ),
                        child: Text(phone, style: Theme.of(context).textTheme.bodyLarge),
                      ),
                      const SizedBox(height: 24),
                      FilledButton.icon(
                        onPressed: _saving ? null : _save,
                        icon: _saving
                            ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                            : const Icon(Icons.save_outlined),
                        label: Text(_saving ? 'Saving…' : 'Save changes'),
                      ),
                    ],
                  ),
                ),
    );
  }
}
