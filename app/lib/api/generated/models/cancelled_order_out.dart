// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'order_status.dart';
import 'quote_out.dart';
import 'refund_out.dart';

part 'cancelled_order_out.g.dart';

@JsonSerializable()
class CancelledOrderOut {
  const CancelledOrderOut({
    required this.createdAt,
    required this.id,
    required this.paidPaise,
    required this.price,
    required this.refund,
    required this.slotId,
    required this.status,
    required this.subsidyApplied,
    required this.version,
  });

  factory CancelledOrderOut.fromJson(Map<String, Object?> json) =>
      _$CancelledOrderOutFromJson(json);

  @JsonKey(name: 'created_at')
  final DateTime createdAt;
  final String id;
  @JsonKey(name: 'paid_paise')
  final int paidPaise;
  final QuoteOut price;
  final RefundOut refund;
  @JsonKey(name: 'slot_id')
  final String slotId;
  final OrderStatus status;
  @JsonKey(name: 'subsidy_applied')
  final bool subsidyApplied;
  final int version;

  Map<String, Object?> toJson() => _$CancelledOrderOutToJson(this);
}
