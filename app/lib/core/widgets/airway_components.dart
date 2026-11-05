import 'package:flutter/material.dart';
import '../theme/airway_colors.dart';
import '../theme/airway_spacing.dart';

/// AIRway reusable UI components shared by customer and worker apps.

class AirwaySectionHeader extends StatelessWidget {
  const AirwaySectionHeader({
    required this.title,
    this.subtitle,
    this.action,
    super.key,
  });

  final String title;
  final String? subtitle;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 21,
                    fontWeight: FontWeight.w800,
                    color: AirwayColors.text,
                  ),
                ),
                if (subtitle != null) ...[
                  const SizedBox(height: 3),
                  Text(
                    subtitle!,
                    style: const TextStyle(
                      fontSize: 12.5,
                      color: AirwayColors.textSecondary,
                    ),
                  ),
                ],
              ],
            ),
          ),
          if (action != null) ...[action!],
        ],
      ),
    );
  }
}

class AirwayServiceCard extends StatelessWidget {
  const AirwayServiceCard({
    required this.title,
    this.categoryName,
    this.subtitle,
    required this.price,
    this.mrp,
    this.isPopular,
    this.image,
    this.onTap,
    super.key,
  });

  final String title;
  final String? categoryName;
  final String? subtitle;
  final double price;
  final double? mrp;
  final bool? isPopular;
  final String? image;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final hasDiscount = mrp != null && mrp! > price;
    return Material(
      color: AirwayColors.surface,
      shape: const ContinuousRectangleBorder(
        side: BorderSide(color: AirwayColors.border),
      ),
      child: Ingram(
        onTap: onTap,
        borderRadius: const BorderRadius.all(Radius.circular(AirwaySpacing.cardRadius)),
        child: Padding(
          padding: const EdgeInsets.all(13),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  _avatar(),
                  const Spacer(),
                  if (isPopular == true)
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        color: AirwayColors.primarySoft,
                        borderRadius: const BorderRadius.all(Radius.circular(9)),
                      ),
                      child: const Text(
                        'Popular',
                        style: TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.w700,
                          color: AirwayColors.primary,
                        ),
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 12),
              Text(
                title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w800,
                  color: AirwayColors.text,
                ),
              ),
              const SizedBox(height: 4),
              Expanded(
                child: Text(
                  subtitle ?? categoryName ?? '',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 11.5,
                    height: 1.25,
                    color: AirwayColors.textSecondary,
                  ),
                ),
              ),
              Row(
                children: [
                  Flexible(
                    child: Text(
                      '₹${price.toStringAsFixed(0)}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w800,
                        color: AirwayColors.primary,
                      ),
                    ),
                  ),
                  if (hasDiscount) ...[
                    const SizedBox(width: 6),
                    Flexible(
                      child: Text(
                        '₹${mrp!.toStringAsFixed(0)}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 11,
                          decoration: TextDecoration.lineThrough,
                          color: AirwayColors.textTertiary,
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _avatar() {
    if (image != null && image!.isNotEmpty) {
      return ClipRRect(
        borderRadius: const BorderRadius.all(Radius.circular(AirwaySpacing.imageRadius)),
        child: Image.network(image!, width: 60, height: 60, fit: BoxFit.cover,
            errorBuilder: (_, _, _) => _placeholder()),
      );
    }
    return _placeholder();
  }

  Widget _placeholder() => Container(
        width: 60,
        height: 60,
        decoration: BoxDecoration(
          color: AirwayColors.primarySoft,
          borderRadius: const BorderRadius.all(Radius.circular(AirwaySpacing.imageRadius)),
        ),
        child: const Icon(Icons.spa_rounded, color: AirwayColors.primary, size: 30),
      );
}

/// A tappable card wrapper used by service cards and lists.
class Ingram extends StatefulWidget {
  const Ingram({
    required this.child,
    this.onTap,
    this.borderRadius,
    super.key,
  });

  final Widget child;
  final VoidCallback? onTap;
  final BorderRadius? borderRadius;

  @override
  State<Ingram> createState() => _IngramState();
}

class _IngramState extends State<Ingram> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: _pressed ? AirwayColors.surfaceVariant : AirwayColors.surface,
      shape: const ContinuousRectangleBorder(
        side: BorderSide(color: AirwayColors.border),
      ),
      child: GestureDetector(
        onTap: widget.onTap,
        onTapDown: (_) => setState(() => _pressed = true),
        onTapUp: (_) => setState(() => _pressed = false),
        onTapCancel: () => setState(() => _pressed = false),
        child: widget.child,
      ),
    );
  }
}