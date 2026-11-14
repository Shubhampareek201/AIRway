import 'package:flutter/material.dart';
import 'package:airway/features/booking/data/booking_api.dart';

/// Shared cart count for customer catalogue screens.
class CustomerCartState {
  CustomerCartState._();

  static final ValueNotifier<int> itemCount = ValueNotifier<int>(0);

  static void updateFromCart(Map<String, dynamic> cart) {
    final items = cart['items'];
    itemCount.value = items is List ? items.length : 0;
  }

  static Future<void> refresh() async {
    try {
      updateFromCart(await BookingApi.getCart());
    } catch (_) {
      // Keep the last known count if a temporary refresh fails.
    }
  }
}

class CustomerCartBadge extends StatefulWidget {
  const CustomerCartBadge({super.key, required this.onTap, this.color});

  final VoidCallback onTap;
  final Color? color;

  @override
  State<CustomerCartBadge> createState() => _CustomerCartBadgeState();
}

class _CustomerCartBadgeState extends State<CustomerCartBadge> {
  @override
  void initState() {
    super.initState();
    CustomerCartState.refresh();
  }

  @override
  Widget build(BuildContext context) {
    return IconButton(
      tooltip: 'Your cart',
      onPressed: widget.onTap,
      icon: ValueListenableBuilder<int>(
        valueListenable: CustomerCartState.itemCount,
        builder: (context, count, _) => Stack(
          clipBehavior: Clip.none,
          children: [
            Icon(Icons.shopping_bag_outlined, color: widget.color),
            if (count > 0)
              Positioned(
                right: -9,
                top: -7,
                child: AnimatedSwitcher(
                  duration: const Duration(milliseconds: 220),
                  transitionBuilder: (child, animation) => ScaleTransition(
                    scale: CurvedAnimation(parent: animation, curve: Curves.elasticOut),
                    child: child,
                  ),
                  child: Container(
                    key: ValueKey<int>(count),
                    constraints: const BoxConstraints(minWidth: 19, minHeight: 19),
                    padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
                    decoration: const BoxDecoration(
                      color: Color(0xFFE53935),
                      shape: BoxShape.circle,
                    ),
                    alignment: Alignment.center,
                    child: Text(
                      count > 99 ? '99+' : '+$count',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 9,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
