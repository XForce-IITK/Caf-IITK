// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'order_refund_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

OrderRefundOut _$OrderRefundOutFromJson(Map<String, dynamic> json) =>
    OrderRefundOut(
      amountPaise: (json['amount_paise'] as num).toInt(),
      at: DateTime.parse(json['at'] as String),
      cause: PaymentCause.fromJson(json['cause'] as String),
      status: PaymentStatus.fromJson(json['status'] as String),
    );

Map<String, dynamic> _$OrderRefundOutToJson(OrderRefundOut instance) =>
    <String, dynamic>{
      'amount_paise': instance.amountPaise,
      'at': instance.at.toIso8601String(),
      'cause': instance.cause,
      'status': instance.status,
    };
