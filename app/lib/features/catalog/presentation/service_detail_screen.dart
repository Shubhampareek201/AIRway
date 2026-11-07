import 'package:flutter/material.dart';
import 'package:airway/features/booking/presentation/booking_scheduled_screen.dart';
import 'package:airway/features/booking/presentation/customer_cart_screen.dart';
import 'package:airway/features/catalog/data/catalog_api.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';
import 'package:airway/features/catalog/data/catalog_image_resolver.dart';

class _Ui {
  static const violet = Color(0xFF315C46);
  static const ink = Color(0xFF1E2923);
  static const sub = Color(0xFF748078);
  static const bg = Color(0xFFFFFFFF);
  static const line = Color(0xFFEAE6DE);
}

class ServiceDetailScreen extends StatefulWidget {
  final int serviceId;
  final int? addressId;
  final Map<String, dynamic> initialAnswers;

  const ServiceDetailScreen({
    super.key,
    required this.serviceId,
    this.addressId,
    this.initialAnswers = const {},
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
      final service = await CatalogApi.getService(
        widget.serviceId,
        addressId: widget.addressId,
      );
      if (mounted) setState(() => _service = service);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  List<ServiceVariant> _matchingVariants(Service service) {
    return service.variants.where((variant) {
      if (variant.attributes.isEmpty) return true;
      return variant.attributes.entries.every((entry) =>
          widget.initialAnswers[entry.key]?.toString() == entry.value.toString());
    }).toList();
  }

  void _navigateToBooking() {
    if (_service == null) return;

    Navigator.push<void>(
      context,
      MaterialPageRoute(
        builder: (_) => BookingScheduledScreen(
          serviceId: _service!.id,
          serviceTitle: _service!.title,
          addressId: widget.addressId,
          initialCategoryAnswers: widget.initialAnswers,
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
        actions: [
          IconButton(
            tooltip: 'Your cart',
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const CustomerCartScreen()),
            ),
            icon: const Icon(Icons.shopping_bag_outlined, color: _Ui.violet),
          ),
        ],
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
        _imageSliver(service),
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
                _infoRow(
                  Icons.access_time_rounded,
                  '${service.durationMinutes} min',
                ),
                if (service.bufferMinutes > 0)
                  _infoRow(
                    Icons.schedule_rounded,
                    '${service.bufferMinutes} min buffer',
                  ),
                if (service.visitFee > 0)
                  _infoRow(
                    Icons.local_atm_rounded,
                    'Visit fee: ₹${service.visitFee.toStringAsFixed(0)}',
                  ),
                if (service.audience != 'all')
                  _infoRow(Icons.person_rounded, service.audienceDisplay),
                if (service.bookingMode == 'inspection' || service.pricingType == 'quote')
                  Padding(
                    padding: const EdgeInsets.only(top: 14),
                    child: Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(13),
                      decoration: BoxDecoration(
                        color: const Color(0xFFFFF7E8),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: const Text(
                        'Inspection required. Any displayed visit fee is for the inspection; the final job quote will be shared after assessment.',
                        style: TextStyle(fontSize: 12, height: 1.45, color: Color(0xFF77551E)),
                      ),
                    ),
                  ),
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
        if (_matchingVariants(service).isNotEmpty) ...[
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
              itemCount: _matchingVariants(service).length,
              separatorBuilder: (_, _) => const SizedBox(height: 10),
              itemBuilder: (context, index) {
                final v = _matchingVariants(service)[index];
                return _variantCard(v, service.categoryName);
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
                return _addonCard(a, service.categoryName);
              },
            ),
          ),
        ],
        const SliverToBoxAdapter(child: SizedBox(height: 16)),
        SliverToBoxAdapter(
          child: Builder(
            builder: (context) {
              return Container(
                color: _Ui.bg,
                padding: const EdgeInsets.symmetric(
                  horizontal: 20,
                  vertical: 12,
                ),
                child: SafeArea(
                  top: false,
                  child: FilledButton(
                    onPressed: _navigateToBooking,
                    child: const Text('Customize & Add to Cart'),
                  ),
                ),
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _imageSliver(Service service) {
    final imageUrls = <String>[
      if (service.image?.isNotEmpty == true) service.image!,
      ...service.images
          .map((item) => item.image)
          .where((image) => image.isNotEmpty),
    ];
    if (imageUrls.isEmpty) {
      imageUrls.add(CatalogImageResolver.forService(
        title: service.title,
        categoryName: service.categoryName,
      ));
    }
    if (imageUrls.isEmpty) {
      return SliverToBoxAdapter(
        child: Container(
          height: 190,
          color: const Color(0xFFEAF1EA),
          alignment: Alignment.center,
          child: const Icon(
            Icons.home_repair_service_rounded,
            color: Color(0xFF315C46),
            size: 52,
          ),
        ),
      );
    }
    return SliverToBoxAdapter(
      child: SizedBox(
        height: 220,
        child: PageView.builder(
          itemCount: imageUrls.length,
          itemBuilder: (context, index) => Image.network(
            imageUrls[index],
            width: double.infinity,
            fit: BoxFit.cover,
            errorBuilder: (_, __, ___) => Container(
              color: const Color(0xFFEAF1EA),
              alignment: Alignment.center,
              child: const Icon(
                Icons.broken_image_outlined,
                color: Color(0xFF987451),
                size: 42,
              ),
            ),
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
        Text(label, style: const TextStyle(fontSize: 14, color: _Ui.ink)),
      ],
    ),
  );

  Widget _variantCard(ServiceVariant v, String categoryName) => Container(
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(
      color: Colors.white,
      borderRadius: BorderRadius.circular(18),
      border: Border.all(color: _Ui.line),
    ),
    child: Row(
      children: [
        if (v.title.isNotEmpty)
          ClipRRect(
            borderRadius: BorderRadius.circular(10),
            child: Image.network(
              v.image?.isNotEmpty == true
                  ? v.image!
                  : CatalogImageResolver.forService(title: v.title, categoryName: categoryName),
              width: 76,
              height: 76,
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => _optionImagePlaceholder(),
            ),
          )
        else
          _optionImagePlaceholder(),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                v.title,
                style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: _Ui.ink),
              ),
              if (v.description?.isNotEmpty == true)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(v.description!, style: const TextStyle(fontSize: 11, color: _Ui.sub)),
                ),
              if (v.includedTasks.isNotEmpty) ...[
                const SizedBox(height: 8),
                ...v.includedTasks.map((task) => Padding(
                  padding: const EdgeInsets.only(top: 3),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Icon(Icons.check_circle_outline, size: 14, color: _Ui.violet),
                      const SizedBox(width: 6),
                      Expanded(child: Text(task, style: const TextStyle(fontSize: 11, color: _Ui.ink))),
                    ],
                  ),
                )),
              ],
              if (v.durationMinutes != null)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text('${v.durationMinutes} min', style: const TextStyle(fontSize: 12, color: _Ui.sub)),
                ),
            ],
          ),
        ),
        const SizedBox(width: 8),
        Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (v.mrp > v.price)
              Text(
                '₹${v.mrp.toStringAsFixed(0)}',
                style: const TextStyle(fontSize: 12, decoration: TextDecoration.lineThrough, color: _Ui.sub),
              ),
            Text(
              v.price > 0 ? '₹${v.price.toStringAsFixed(0)}' : 'Price on request',
              textAlign: TextAlign.end,
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w800, color: _Ui.violet),
            ),
            if (v.discountPercent > 0)
              Text('${v.discountPercent}% OFF', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: Color(0xFF7861A8))),
          ],
        ),
      ],
    ),
  );

  Widget _addonCard(AddOn a, String categoryName) => Container(
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(
      color: Colors.white,
      borderRadius: BorderRadius.circular(14),
      border: Border.all(color: _Ui.line),
    ),
    child: Row(
      children: [
        if (a.title.isNotEmpty)
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: Image.network(
              a.image?.isNotEmpty == true
                  ? a.image!
                  : CatalogImageResolver.forService(title: a.title, categoryName: categoryName),
              width: 58,
              height: 58,
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => _optionImagePlaceholder(size: 58),
            ),
          )
        else
          _optionImagePlaceholder(size: 58),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                a.title,
                style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                  color: _Ui.ink,
                ),
              ),
              if (a.description?.isNotEmpty == true)
                Padding(
                  padding: const EdgeInsets.only(top: 3),
                  child: Text(a.description!, style: const TextStyle(fontSize: 11, color: _Ui.sub)),
                ),
            ],
          ),
        ),
        Text(
          a.price > 0 ? '₹${a.price.toStringAsFixed(0)}' : 'Price on request',
          textAlign: TextAlign.end,
          style: const TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w800,
            color: _Ui.violet,
          ),
        ),
      ],
    ),
  );

  Widget _optionImagePlaceholder({double size = 76}) => Container(
    width: size,
    height: size,
    decoration: BoxDecoration(
      color: const Color(0xFFEAF1EA),
      borderRadius: BorderRadius.circular(10),
    ),
    alignment: Alignment.center,
    child: const Icon(Icons.photo_outlined, color: Color(0xFF748078), size: 25),
  );

  Widget _errorWidget(String message) => Center(
    child: Padding(
      padding: const EdgeInsets.all(28),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.error_outline, color: Colors.redAccent, size: 52),
          const SizedBox(height: 14),
          Text(
            message,
            textAlign: TextAlign.center,
            style: const TextStyle(color: _Ui.sub),
          ),
          const SizedBox(height: 20),
          FilledButton(onPressed: _loadService, child: const Text('Retry')),
        ],
      ),
    ),
  );
}
