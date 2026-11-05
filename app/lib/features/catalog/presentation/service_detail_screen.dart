import 'package:flutter/material.dart';
import 'package:airway/features/booking/presentation/booking_scheduled_screen.dart';
import 'package:airway/features/catalog/data/catalog_api.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';

class _Ui {
  static const violet = Color(0xFF6F4EF6);
  static const ink = Color(0xFF201A33);
  static const sub = Color(0xFF78718B);
  static const bg = Color(0xFFF8F7FD);
  static const pale = Color(0xFFF1EDFF);
  static const line = Color(0xFFEAE5F5);
}

class ServiceDetailScreen extends StatefulWidget {
  final int serviceId;

  const ServiceDetailScreen({
    super.key,
    required this.serviceId,
  });

  @override
  State<ServiceDetailScreen> createState() => _ServiceDetailScreenState();
}

class _ServiceDetailScreenState extends State<ServiceDetailScreen> {
  Service? _service;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadService();
  }

  Future<void> _loadService() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final service = await CatalogApi.getService(widget.serviceId);
      if (mounted) setState(() => _service = service);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _navigateToBooking() {
    if (_service == null) return;

    final mode = _service!.bookingMode;
    if (mode != 'scheduled' && mode != 'pickup_drop') {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'This service uses "${_service!.bookingModeDisplay}" booking mode. '
            'Please contact us directly to arrange it.',
          ),
          backgroundColor: Colors.orange,
          duration: const Duration(seconds: 4),
        ),
      );
      return;
    }

    Navigator.push<void>(
      context,
      MaterialPageRoute(
        builder: (_) => BookingScheduledScreen(
          serviceId: _service!.id,
          serviceTitle: _service!.title,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _Ui.bg,
      appBar: AppBar(
        title: Text(_service?.title ?? 'Service'),
        backgroundColor: _Ui.bg,
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: _Ui.violet))
          : _error != null
              ? _errorWidget(_error!)
              : _service == null
                  ? _errorWidget('Service not found.')
                  : _buildBody(),
    );
  }

  Widget _buildBody() {
    final service = _service!;
    return CustomScrollView(
      slivers: [
        _imageSliver(service.image),
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  service.title,
                  style: const TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.w900,
                    color: _Ui.ink,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  service.categoryName,
                  style: const TextStyle(
                    fontSize: 14,
                    color: _Ui.sub,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                if (service.description?.isNotEmpty ?? false) ...[
                  const SizedBox(height: 12),
                  Text(
                    service.description!,
                    style: const TextStyle(
                      fontSize: 14,
                      height: 1.6,
                      color: _Ui.ink,
                    ),
                  ),
                ],
                const SizedBox(height: 16),
                _infoRow(Icons.access_time_rounded, '${service.durationMinutes} min'),
                if (service.bufferMinutes > 0)
                  _infoRow(Icons.schedule_rounded, '${service.bufferMinutes} min buffer'),
                if (service.visitFee > 0)
                  _infoRow(Icons.local_atm_rounded, 'Visit fee: ₹${service.visitFee.toStringAsFixed(0)}'),
                if (service.audience != 'all')
                  _infoRow(Icons.person_rounded, service.audienceDisplay),
                if (service.requiresFemaleWorker)
                  const Padding(
                    padding: EdgeInsets.only(top: 6),
                    child: Text(
                      'Female worker available on request',
                      style: TextStyle(fontSize: 12, color: _Ui.sub),
                    ),
                  ),
              ],
            ),
          ),
        ),
        if (service.variants.isNotEmpty) ...[
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
              child: const Text(
                'Packages',
                style: TextStyle(
                  fontSize: 17,
                  fontWeight: FontWeight.w800,
                  color: _Ui.ink,
                ),
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: ListView.separated(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemCount: service.variants.length,
              separatorBuilder: (_, _) => const SizedBox(height: 10),
              itemBuilder: (context, index) {
                final v = service.variants[index];
                return _variantCard(v);
              },
            ),
          ),
        ],
        if (service.addons.isNotEmpty) ...[
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
              child: const Text(
                'Add-ons',
                style: TextStyle(
                  fontSize: 17,
                  fontWeight: FontWeight.w800,
                  color: _Ui.ink,
                ),
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: ListView.separated(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemCount: service.addons.length,
              separatorBuilder: (_, _) => const SizedBox(height: 10),
              itemBuilder: (context, index) {
                final a = service.addons[index];
                return _addonCard(a);
              },
            ),
          ),
        ],
        SliverToBoxAdapter(
          child: Padding(
            padding:
                const EdgeInsets.fromLTRB(20, 16, 20, 16),
            child: _formSection(service.formFields),
          ),
        ),
        const SliverToBoxAdapter(child: SizedBox(height: 16)),
        SliverToBoxAdapter(
          child: Builder(builder: (context) {
            return Container(
              color: _Ui.bg,
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
              child: SafeArea(
                top: false,
                child: FilledButton(
                  onPressed: _navigateToBooking,
                  child: const Text('Book Now'),
                ),
              ),
            );
          }),
        ),
      ],
    );
  }


  Widget _imageSliver(String? imageUrl) {
    if (imageUrl == null || imageUrl.isEmpty) {
      return const SliverToBoxAdapter(child: SizedBox(height: 20));
    }
    return SliverToBoxAdapter(
      child: Container(
        height: 200,
        decoration: BoxDecoration(
          image: DecorationImage(
            image: NetworkImage(imageUrl),
            fit: BoxFit.cover,
          ),
        ),
      ),
    );
  }

  Widget _infoRow(IconData icon, String label) => Padding(
        padding: const EdgeInsets.only(top: 6),
        child: Row(
          children: [
            Icon(icon, size: 18, color: _Ui.violet),
            const SizedBox(width: 8),
            Text(label,
                style: const TextStyle(
                    fontSize: 14, color: _Ui.ink)),
          ],
        ),
      );

  Widget _variantCard(ServiceVariant v) => Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: _Ui.line),
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(v.title,
                      style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w800,
                          color: _Ui.ink)),
                  if (v.durationMinutes != null)
                    Text(
                      '${v.durationMinutes} min',
                      style: const TextStyle(
                          fontSize: 12, color: _Ui.sub),
                    ),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                if (v.mrp > v.price)
                  Text(
                    '₹${v.mrp.toStringAsFixed(0)}',
                    style: const TextStyle(
                      fontSize: 12,
                      decoration:
                          TextDecoration.lineThrough,
                      color: _Ui.sub,
                    ),
                  ),
                Text(
                  '₹${v.price.toStringAsFixed(0)}',
                  style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w800,
                      color: _Ui.violet),
                ),
                if (v.discountPercent > 0)
                  Text(
                    '${v.discountPercent}% OFF',
                    style: const TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF0F9F91)),
                  ),
              ],
            ),
          ],
        ),
      );

  Widget _addonCard(AddOn a) => Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: _Ui.line),
        ),
        child: Row(
          children: [
            Expanded(
              child: Text(a.title,
                  style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: _Ui.ink)),
            ),
            Text(
              '₹${a.price.toStringAsFixed(0)}',
              style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w800,
                  color: _Ui.violet),
            ),
          ],
        ),
      );

  Widget _formSection(List<CatalogFormField> fields) {
    if (fields.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Details needed',
          style: TextStyle(
              fontSize: 17,
              fontWeight: FontWeight.w800,
              color: _Ui.ink),
        ),
        const SizedBox(height: 12),
        for (final f in fields) ...[
          _formField(f),
          const SizedBox(height: 12),
        ],
      ],
    );
  }

  Widget _formField(CatalogFormField f) {
    final widget = switch (f.fieldType) {
      'number' => TextFormField(
          decoration: InputDecoration(
            labelText: f.label,
            hintText: f.label,
            border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12)),
          ),
          keyboardType: TextInputType.number,
        ),
      'textarea' => TextFormField(
          decoration: InputDecoration(
            labelText: f.label,
            hintText: f.label,
            border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12)),
          ),
          maxLines: 3,
        ),
      'select' => DropdownButtonFormField<String>(
          decoration: InputDecoration(
            labelText: f.label,
            border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12)),
          ),
          items: f.options
              .map((e) => DropdownMenuItem(
                  value: e.toString(),
                  child: Text(e.toString())))
              .toList(),
          onChanged: (_) {},
          validator: (v) =>
              f.isRequired && (v?.isEmpty ?? true)
                  ? 'Required'
                  : null,
        ),
      'photo' => InkWell(
          onTap: () {},
          child: Container(
            height: 100,
            decoration: BoxDecoration(
              color: _Ui.pale,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: _Ui.line),
            ),
            child: const Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.camera_alt_rounded,
                      color: _Ui.violet, size: 28),
                  SizedBox(height: 4),
                  Text('Tap to add photo',
                      style: TextStyle(
                          color: _Ui.sub, fontSize: 12)),
                ],
              ),
            ),
          ),
        ),
      _ => TextFormField(
          decoration: InputDecoration(
            labelText: f.label,
            hintText: f.label,
            border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12)),
          ),
        ),
    };

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '${f.label}${f.isRequired ? ' *' : ''}',
          style: const TextStyle(
              fontSize: 13, fontWeight: FontWeight.w600, color: _Ui.ink),
        ),
        const SizedBox(height: 4),
        widget,
      ],
    );
  }

  Widget _errorWidget(String message) => Center(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline,
                  color: Colors.redAccent, size: 52),
              const SizedBox(height: 14),
              Text(
                message,
                textAlign: TextAlign.center,
                style: const TextStyle(color: _Ui.sub),
              ),
              const SizedBox(height: 20),
              FilledButton(
                onPressed: _loadService,
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      );
}
