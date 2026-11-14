import 'package:flutter/material.dart';
import 'package:airway/features/catalog/data/beauty_audience.dart';

/// First step of the Beauty journey: explicitly choose the intended audience.
/// "Both" is limited to catalogue services configured as unisex.
class BeautyAudienceScreen extends StatelessWidget {
  static const _green = Color(0xFF315C46);
  static const _ink = Color(0xFF1E2923);
  static const _muted = Color(0xFF748078);
  static const _line = Color(0xFFEAE6DE);

  static const _menImage =
      'https://images.unsplash.com/photo-1503951914875-452162b0f3f1?w=900&auto=format&fit=crop';
  static const _womenImage =
      'https://images.unsplash.com/photo-1560066984-138dadb4c035?w=900&auto=format&fit=crop';

  final List<Map<String, dynamic>> options;

  const BeautyAudienceScreen({super.key, this.options = const []});

  static Future<String?> choose(
    BuildContext context, {
    List<Map<String, dynamic>> options = const [],
  }) {
    return Navigator.push<String>(
      context,
      MaterialPageRoute(builder: (_) => BeautyAudienceScreen(options: options)),
    );
  }

  List<Map<String, dynamic>> get _visibleOptions {
    final configured = options.where((item) => item['is_active'] != false).toList()
      ..sort((a, b) => (a['sort_order'] as num? ?? 0).compareTo(b['sort_order'] as num? ?? 0));
    if (configured.isNotEmpty) return configured;
    return const [
      {'audience': 'men', 'title': 'Men', 'subtitle': 'Haircut, beard, grooming and more', 'image': _menImage},
      {'audience': 'women', 'title': 'Women', 'subtitle': 'Hair, skin care, makeup and more', 'image': _womenImage},
      {'audience': 'both', 'title': 'Both', 'subtitle': 'Unisex services for everyone', 'image': _menImage, 'image_secondary': _womenImage},
    ];
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF8F8F5),
      appBar: AppBar(
        title: const Text('Beauty & Salon'),
        backgroundColor: const Color(0xFFF8F8F5),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(0, 12, 0, 28),
        children: [
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 20),
            child: Text(
            'Who are you booking for?',
            style: TextStyle(
              color: _ink,
              fontSize: 25,
              fontWeight: FontWeight.w900,
            ),
          ),
          ),
          const SizedBox(height: 7),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 20),
            child: Text(
              'Choose an option to see the right salon services.',
              style: TextStyle(color: _muted, height: 1.45),
            ),
          ),
          const SizedBox(height: 22),
          for (final option in _visibleOptions) ...[
            _audienceCard(
              context,
              value: option['audience']?.toString() ?? '',
              title: option['title']?.toString() ?? '',
              subtitle: option['subtitle']?.toString() ?? '',
              image: option['image']?.toString() ?? '',
              secondaryImage: option['image_secondary']?.toString() ?? '',
            ),
            const SizedBox(height: 14),
          ],
          const SizedBox(height: 16),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 20),
            child: Text(
              'Your selection only filters the services; it does not determine your professional preference.',
              textAlign: TextAlign.center,
              style: TextStyle(color: _muted, fontSize: 11, height: 1.45),
            ),
          ),
        ],
      ),
    );
  }

  Widget _audienceCard(
    BuildContext context, {
    required String value,
    required String title,
    required String subtitle,
    required String image,
    required String secondaryImage,
  }) {
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.zero,
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => Navigator.pop(context, value),
        child: Container(
          decoration: BoxDecoration(
            border: Border.all(color: _line),
            borderRadius: BorderRadius.circular(20),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (value == BeautyAudience.both && image.isNotEmpty && secondaryImage.isNotEmpty)
                SizedBox(
                  height: 57,
                  child: Row(
                    children: [
                      Expanded(child: Image.network(image, height: 174, width: double.infinity, fit: BoxFit.cover, errorBuilder: (_, __, ___) => _imageFallback())),
                      Expanded(child: Image.network(secondaryImage, height: 174, width: double.infinity, fit: BoxFit.cover, errorBuilder: (_, __, ___) => _imageFallback())),
                    ],
                  ),
                )
              else if (image.isNotEmpty)
                SizedBox(
                  height: 174,
                  width: double.infinity,
                  child: Image.network(
                    image,
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) => _imageFallback(),
                  ),
                ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 9),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(title, style: const TextStyle(
                            color: _ink, fontSize: 16, fontWeight: FontWeight.w900,
                          )),
                          const SizedBox(height: 3),
                          Text(subtitle, style: const TextStyle(
                            color: _muted, fontSize: 11,
                          )),
                        ],
                      ),
                    ),
                    const Icon(Icons.arrow_forward_rounded, color: _green),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _bothCard(BuildContext context) {
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(20),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => Navigator.pop(context, BeautyAudience.both),
        child: Container(
          decoration: BoxDecoration(
            border: Border.all(color: _line),
            borderRadius: BorderRadius.circular(20),
          ),
          child: Column(
            children: [
              SizedBox(
                height: 174,
                child: Row(
                  children: [
                    Expanded(
                      child: Image.network(
                        _menImage,
                        height: 174,
                        fit: BoxFit.cover,
                        errorBuilder: (_, __, ___) => _imageFallback(),
                      ),
                    ),
                    Expanded(
                      child: Image.network(
                        _womenImage,
                        height: 174,
                        fit: BoxFit.cover,
                        errorBuilder: (_, __, ___) => _imageFallback(),
                      ),
                    ),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 13, 16, 15),
                child: Row(
                  children: [
                    const Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Both', style: TextStyle(
                            color: _ink, fontSize: 18, fontWeight: FontWeight.w900,
                          )),
                          SizedBox(height: 3),
                          Text('Unisex services for everyone', style: TextStyle(
                            color: _muted, fontSize: 12,
                          )),
                        ],
                      ),
                    ),
                    const Icon(Icons.arrow_forward_rounded, color: _green),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _imageFallback() => Container(
    color: const Color(0xFFEAF1EA),
    alignment: Alignment.center,
    child: const Icon(Icons.spa_outlined, color: _green, size: 28),
  );
}
