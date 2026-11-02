// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'payment_cause.dart';
import 'payment_status.dart';

part 'order_refund_out.g.dart';

@JsonSerializable()
class OrderRefundOut {
  const OrderRefundOut({
    required this.amountPaise,
    required this.at,
    required this.cause,
    required this.status,
  });

  factory OrderRefundOut.fromJson(Map<String, Object?> json) =>
      _$OrderRefundOutFromJson(json);

  @JsonKey(name: 'amount_paise')
  final int amountPaise;
  final DateTime at;
  final PaymentCause cause;
  final PaymentStatus status;

  Map<String, Object?> toJson() => _$OrderRefundOutToJson(this);
}
