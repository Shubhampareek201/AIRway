import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/ratings/data/rating_models.dart';
import 'package:airway/features/ratings/data/rating_api.dart';

class RatingsScreen extends StatefulWidget {
  const RatingsScreen({super.key});

  @override
  State<RatingsScreen> createState() => _RatingsScreenState();
}

class _RatingsScreenState extends State<RatingsScreen> {
  List<RatingModel> _ratings = [];
  RatingSummaryModel? _summary;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (mounted) setState(() => _loading = true);
    try {
      final ratings = await RatingApi.fetchUserRatings();
      final summary = await RatingApi.fetchRatingSummary();
      if (mounted) {
        setState(() {
          _ratings = ratings;
          _summary = summary;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
          _loading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Your Ratings')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text('Error: $_error'))
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView(padding: const EdgeInsets.all(16), children: [
                    _buildSummaryCard(),
                    const SizedBox(height: 16),
                    const Text('Rating History',
                        style: TextStyle(
                            fontSize: 18, fontWeight: FontWeight.w800)),
                    const SizedBox(height: 8),
                    if (_ratings.isEmpty)
                      const Text('No ratings yet.',
                          style: TextStyle(color: Colors.grey))
                    else
                      ..._ratings.map((r) => _RatingTile(rating: r)),
                  ]),
                ),
    );
  }

  Widget _buildSummaryCard() {
    if (_summary == null) {
      return const SizedBox.shrink();
    }
    final avg = _summary!.averageRating;
    final count = _summary!.totalRatings;
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: AirwayColors.primaryGradient,
        borderRadius: BorderRadius.circular(24),
      ),
      child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
        const Text('Your Rating',
            style: TextStyle(color: Colors.white70, fontSize: 13)),
        const SizedBox(height: 6),
        Row(children: [
          Icon(Icons.star_rounded,
              size: 32, color: AirwayColors.gold),
          const SizedBox(width: 8),
          Text('$avg',
              style: const TextStyle(
                  color: Colors.white,
                  fontSize: 32,
                  fontWeight: FontWeight.w900)),
          const Spacer(),
          Text('($count ${count == 1 ? 'rating' : 'ratings'})',
              style: const TextStyle(color: Colors.white70, fontSize: 11)),
        ]),
      ]),
    );
  }
}

class _RatingTile extends StatelessWidget {
  final RatingModel rating;
  const _RatingTile({required this.rating});

  @override
  Widget build(BuildContext context) {
    final isCustomer = rating.ratingType == 'customer';
    final title = isCustomer ? 'Worker rating' : 'Customer rating';
    final subtitle = 'Booking #${rating.bookingId} • ${rating.createdAt}';
    return Card(
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: rating.rating >= 4
              ? AirwayColors.success.withAlpha(30)
              : rating.rating >= 3
                  ? AirwayColors.warning.withAlpha(30)
                  : AirwayColors.error.withAlpha(30),
          child: Icon(Icons.star_rounded,
              color: rating.rating >= 4
                  ? AirwayColors.success
                  : rating.rating >= 3
                      ? AirwayColors.warning
                      : AirwayColors.error,
              size: 20),
        ),
        title: Text(title),
        subtitle: Text(subtitle),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('${rating.rating}/5',
                style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    color: Colors.black87)),
            const SizedBox(width: 4),
            const Icon(Icons.star_rounded,
                size: 16, color: Color(0xFFFFB020)),
          ],
        ),
      ),
    );
  }
}