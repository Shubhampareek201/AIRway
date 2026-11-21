import 'dart:io';
import 'package:airway/core/localization/airway_text.dart';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:airway/features/booking/data/booking_api.dart';
import 'package:airway/features/booking/presentation/customer_cart_badge.dart';
import 'package:airway/features/booking/presentation/customer_cart_screen.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';

class ElectricalIssueDetailsScreen extends StatefulWidget {
  const ElectricalIssueDetailsScreen({
    super.key,
    required this.service,
    this.variant,
    required this.categoryAnswers,
  });

  final Service service;
  final ServiceVariant? variant;
  final Map<String, dynamic> categoryAnswers;

  @override
  State<ElectricalIssueDetailsScreen> createState() =>
      _ElectricalIssueDetailsScreenState();
}

class _ElectricalIssueDetailsScreenState
    extends State<ElectricalIssueDetailsScreen> {
  static const violet = Color(0xFF315C46);
  static const ink = Color(0xFF1E2923);
  static const muted = Color(0xFF748078);
  final _notesController = TextEditingController();
  final _picker = ImagePicker();
  File? _photo;
  bool _saving = false;

  @override
  void dispose() {
    _notesController.dispose();
    super.dispose();
  }

  Future<void> _pickPhoto(ImageSource source) async {
    try {
      final picked = await _picker.pickImage(
        source: source,
        imageQuality: 82,
        maxWidth: 1600,
        maxHeight: 1600,
      );
      if (picked != null && mounted) {
        setState(() => _photo = File(picked.path));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(AirwayText.tr('Could not select photo: $e', 'फ़ोटो चुन नहीं सके: $e'))),
        );
      }
    }
  }

  Future<void> _addToCart() async {
    if (_saving) return;
    setState(() => _saving = true);
    int? createdItemId;
    try {
      final cart = await BookingApi.addCartItem(
        serviceId: widget.service.id,
        variantId: widget.variant?.id,
        quantity: 1,
        addonSelections: const [],
        formAnswers: const {},
        categoryAnswers: widget.categoryAnswers,
        notes: _notesController.text.trim(),
      );
      createdItemId = int.tryParse(cart['added_item_id']?.toString() ?? '');
      if (createdItemId == null) {
        throw Exception('The service was not added to the cart. Please try again.');
      }
      if (_photo != null) {
        await BookingApi.uploadCartItemIssuePhoto(
          itemId: createdItemId,
          photo: _photo!,
        );
      }
      CustomerCartState.updateFromCart(cart);
      if (!mounted) return;
      Navigator.pop(context, true);
    } catch (e) {
      // Do not leave a duplicate/half-configured cart line after a failed upload.
      if (createdItemId != null) {
        try {
          await BookingApi.deleteCartItem(createdItemId);
        } catch (_) {
          // Keep the original failure visible; the cart can be refreshed safely.
        }
      }
      if (mounted) {
        setState(() => _saving = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(AirwayText.tr('Could not add service: $e', 'सेवा नहीं जोड़ी जा सकी: $e'))),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final visitFee = widget.service.bookingMode == 'inspection'
        ? widget.service.visitFee
        : 0.0;
    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        title: Text(AirwayText.tr('Describe the issue', 'समस्या का विवरण दें')),
        backgroundColor: Colors.white,
        actions: [
          CustomerCartBadge(
            color: violet,
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const CustomerCartScreen()),
            ),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text(widget.service.title,
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w900, color: ink)),
          const SizedBox(height: 5),
          if (widget.variant?.title.isNotEmpty == true)
            Text(widget.variant!.title,
                style: const TextStyle(fontSize: 14, color: muted)),
          const SizedBox(height: 18),
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: const Color(0xFFF7F8F6),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: const Color(0xFFEAE6DE)),
            ),
            child: Column(
              children: [
                _priceRow('Service price', widget.variant == null ? 'Quote after assessment' : '₹${widget.variant!.price.toStringAsFixed(0)}'),
                if (visitFee > 0) ...[
                  const SizedBox(height: 8),
                  _priceRow('Inspection / visit charge', '₹${visitFee.toStringAsFixed(0)}'),
                ],
                const Divider(height: 20),
                _priceRow(
                  'Before applicable taxes',
                  widget.variant == null ? 'Quote after assessment' : '₹${(widget.variant!.price + visitFee).toStringAsFixed(0)}',
                  bold: true,
                ),
                if (visitFee > 0)
                  const Padding(
                    padding: EdgeInsets.only(top: 8),
                    child: Text(
                      'The visit charge is set by AIRway and is charged once for this inspection. Any repair cost will be confirmed after assessment.',
                      style: TextStyle(fontSize: 11, height: 1.4, color: muted),
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          Text(AirwayText.tr('Add a photo (optional)', 'फ़ोटो जोड़ें (वैकल्पिक)'),
              style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: ink)),
          const SizedBox(height: 6),
          const Text('A photo helps the professional understand the problem before visiting.',
              style: TextStyle(fontSize: 12, color: muted)),
          const SizedBox(height: 12),
          if (_photo != null) ...[
            ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: Image.file(_photo!, height: 190, width: double.infinity, fit: BoxFit.cover),
            ),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                onPressed: _saving ? null : () => setState(() => _photo = null),
                icon: const Icon(Icons.delete_outline),
                label: Text(AirwayText.tr('Remove photo', 'फ़ोटो हटाएँ')),
              ),
            ),
          ] else
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _saving ? null : () => _pickPhoto(ImageSource.camera),
                    icon: const Icon(Icons.camera_alt_outlined),
                    label: Text(AirwayText.tr('Camera', 'कैमरा')),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _saving ? null : () => _pickPhoto(ImageSource.gallery),
                    icon: const Icon(Icons.photo_library_outlined),
                    label: Text(AirwayText.tr('Gallery', 'गैलरी')),
                  ),
                ),
              ],
            ),
          const SizedBox(height: 22),
          Text(AirwayText.tr('Describe the problem (optional)', 'समस्या बताएँ (वैकल्पिक)'),
              style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: ink)),
          const SizedBox(height: 10),
          TextField(
            controller: _notesController,
            minLines: 3,
            maxLines: 5,
            maxLength: 1000,
            textCapitalization: TextCapitalization.sentences,
            decoration: InputDecoration(
              hintText: AirwayText.tr('Example: The ceiling fan is making a noise...', 'उदाहरण: छत का पंखा आवाज़ कर रहा है...'),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: Color(0xFFEAE6DE)),
              ),
            ),
          ),
          const SizedBox(height: 24),
        ],
      ),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 10, 20, 18),
          child: SizedBox(
            height: 52,
            child: FilledButton(
              onPressed: _saving ? null : _addToCart,
              style: FilledButton.styleFrom(backgroundColor: violet),
              child: _saving
                  ? const SizedBox(
                      width: 20, height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                    )
                  : Text(AirwayText.tr('ADD TO CART', 'कार्ट में जोड़ें')),
            ),
          ),
        ),
      ),
    );
  }

  Widget _priceRow(String label, String value, {bool bold = false}) => Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: TextStyle(
            fontSize: 13,
            color: bold ? ink : muted,
            fontWeight: bold ? FontWeight.w800 : FontWeight.w500,
          )),
          Text(value, style: TextStyle(
            fontSize: 14,
            color: ink,
            fontWeight: bold ? FontWeight.w900 : FontWeight.w700,
          )),
        ],
      );
}
