// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'payment_status.dart';

part 'refund_out.g.dart';

@JsonSerializable()
class RefundOut {
  const RefundOut({required this.amountPaise, required this.status});

  factory RefundOut.fromJson(Map<String, Object?> json) =>
      _$RefundOutFromJson(json);

  @JsonKey(name: 'amount_paise')
  final int amountPaise;
  final PaymentStatus status;

  Map<String, Object?> toJson() => _$RefundOutToJson(this);
}
