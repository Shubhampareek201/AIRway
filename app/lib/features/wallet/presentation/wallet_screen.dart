import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/wallet/data/wallet_api.dart';
import 'package:airway/features/wallet/data/wallet_models.dart';

class WalletScreen extends StatefulWidget {
  const WalletScreen({super.key});

  @override
  State<WalletScreen> createState() => _WalletScreenState();
}

class _WalletScreenState extends State<WalletScreen> {
  WalletModel? _wallet;
  List<WalletTransactionModel> _transactions = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (mounted) setState(() => _loading = true);
    try {
      final balance = await WalletApi.fetchBalance();
      final tx = await WalletApi.fetchTransactions();
      if (mounted) {
        setState(() {
          _wallet = balance;
          _transactions = tx;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() => _loading = false);
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Could not load wallet.')));
      }
    }
  }

  Future<void> _showTopUpDialog() async {
    final amounts = [100.0, 200.0, 500.0, 1000.0];
    double? selected;
    final customController = TextEditingController();
    showDialog<void>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialog) => AlertDialog(
          title: const Text('Add money to wallet'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Wrap(spacing: 8, runSpacing: 8, children: amounts.map((v) {
                return ChoiceChip(
                  label: Text('Rs ${v.toStringAsFixed(0)}'),
                  selected: selected == v,
                  onSelected: (val) { selected = val as double; setDialog(() {}); },
                );
              }).toList()),
              const SizedBox(height: 12),
              TextField(
                controller: customController,
                decoration: const InputDecoration(labelText: 'Or enter custom amount'),
                style: const TextStyle(),
                keyboardType: TextInputType.number,
                enabled: true,
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
            TextButton(
              onPressed: () async {
                final amount = selected ?? double.tryParse(customController.text);
                if (amount == null || amount <= 0) return;
                Navigator.pop(ctx);
                try {
                  await WalletApi.topUp(amount: amount);
                  if (mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Top-up request submitted.')));
                    _load();
                  }
                } catch (e) {
                  if (mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString())));
                  }
                }
              },
              child: const Text('Confirm'),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('AIRway Wallet')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  _BalanceCard(balance: _wallet?.balance ?? 0, pending: _wallet?.pendingBalance ?? 0),
                  const SizedBox(height: 16),
                  FilledButton.icon(
                    onPressed: _showTopUpDialog,
                    icon: const Icon(Icons.add_circle_outlined),
                    label: const Text('Add money'),
                  ),
                  const SizedBox(height: 24),
                  const Text('Transaction history', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
                  const SizedBox(height: 8),
                  if (_transactions.isEmpty)
                    const Text('No transactions yet.'),
                  for (final t in _transactions) _TransactionTile(tx: t),
                ],
              ),
            ),
    );
  }
}

class _BalanceCard extends StatelessWidget {
  final double balance;
  final double pending;
  const _BalanceCard({required this.balance, required this.pending});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: AirwayColors.primaryGradient,
        borderRadius: BorderRadius.circular(24),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Available balance', style: TextStyle(color: Colors.white70, fontSize: 13)),
        const SizedBox(height: 6),
        Text('Rs ${balance.toStringAsFixed(2)}', style: const TextStyle(color: Colors.white, fontSize: 30, fontWeight: FontWeight.w900)),
        const SizedBox(height: 12),
        Text('Pending: Rs ${pending.toStringAsFixed(2)}', style: const TextStyle(color: Colors.white70, fontSize: 12)),
      ]),
    );
  }
}

class _TransactionTile extends StatelessWidget {
  final WalletTransactionModel tx;
  const _TransactionTile({required this.tx});

  @override
  Widget build(BuildContext context) {
    final isCredit = tx.type == 'credit' || tx.type == 'refund' || tx.type == 'cashback';
    final sign = isCredit ? '+' : '-';
    final color = isCredit ? AirwayColors.success : AirwayColors.error;
    return Card(
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: color.withAlpha(20),
          child: Icon(isCredit ? Icons.arrow_downward : Icons.arrow_upward, color: color, size: 20),
        ),
        title: Text(tx.typeDisplay),
        subtitle: Text(tx.description),
        trailing: Text('$sign Rs ${tx.amount.toStringAsFixed(2)}', style: TextStyle(color: color, fontWeight: FontWeight.w700)),
      ),
    );
  }
}
