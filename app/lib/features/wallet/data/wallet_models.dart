class WalletTransactionModel {
  final int id;
  final String type;
  final String typeDisplay;
  final double amount;
  final String description;
  final String status;
  final String statusDisplay;
  final String referenceId;
  final String createdAt;

  WalletTransactionModel({
    required this.id,
    required this.type,
    required this.typeDisplay,
    required this.amount,
    required this.description,
    required this.status,
    required this.statusDisplay,
    required this.referenceId,
    required this.createdAt,
  });

  factory WalletTransactionModel.fromMap(Map<String, dynamic> map) {
    return WalletTransactionModel(
      id: map['id'] as int,
      type: (map['type'] as String?) ?? '',
      typeDisplay: (map['type_display'] as String?) ?? '',
      amount: double.tryParse((map['amount'] ?? '0').toString()) ?? 0,
      description: (map['description'] as String?) ?? '',
      status: (map['status'] as String?) ?? '',
      statusDisplay: (map['status_display'] as String?) ?? '',
      referenceId: (map['reference_id'] as String?) ?? '',
      createdAt: (map['created_at'] as String?) ?? '',
    );
  }
}

class WalletModel {
  final int id;
  final double balance;
  final double pendingBalance;
  final List<WalletTransactionModel> transactions;
  final String createdAt;

  WalletModel({
    required this.id,
    required this.balance,
    required this.pendingBalance,
    required this.transactions,
    required this.createdAt,
  });

  factory WalletModel.fromMap(Map<String, dynamic> map) {
    final tx = map['transactions'];
    final list = tx is List
        ? tx
            .map((e) => WalletTransactionModel.fromMap(e as Map<String, dynamic>))
            .toList()
        : <WalletTransactionModel>[];
    return WalletModel(
      id: map['id'] as int,
      balance: double.tryParse((map['balance'] ?? '0').toString()) ?? 0,
      pendingBalance:
          double.tryParse((map['pending_balance'] ?? '0').toString()) ?? 0,
      transactions: list,
      createdAt: (map['created_at'] as String?) ?? '',
    );
  }
}