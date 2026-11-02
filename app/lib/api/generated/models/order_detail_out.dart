// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'order_refund_out.dart';
import 'order_status.dart';
import 'quote_out.dart';
import 'snapshot_out.dart';
import 'transition_out.dart';

part 'order_detail_out.g.dart';

/// FR-40 and FR-28: the order, every state change so far, every price snapshot.
/// version and every refund, each oldest first.
@JsonSerializable()
class OrderDetailOut {
  const OrderDetailOut({
    required this.createdAt,
    required this.history,
    required this.id,
    required this.paidPaise,
    required this.price,
    required this.refunds,
    required this.slotId,
    required this.snapshots,
    required this.status,
    required this.subsidyApplied,
    required this.version,
  });

  factory OrderDetailOut.fromJson(Map<String, Object?> json) =>
      _$OrderDetailOutFromJson(json);

  @JsonKey(name: 'created_at')
  final DateTime createdAt;
  final List<TransitionOut> history;
  final String id;
  @JsonKey(name: 'paid_paise')
  final int paidPaise;
  final QuoteOut price;
  final List<OrderRefundOut> refunds;
  @JsonKey(name: 'slot_id')
  final String slotId;
  final List<SnapshotOut> snapshots;
  final OrderStatus status;
  @JsonKey(name: 'subsidy_applied')
  final bool subsidyApplied;
  final int version;

  Map<String, Object?> toJson() => _$OrderDetailOutToJson(this);
}
