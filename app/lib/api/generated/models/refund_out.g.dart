// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'refund_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

RefundOut _$RefundOutFromJson(Map<String, dynamic> json) => RefundOut(
  amountPaise: (json['amount_paise'] as num).toInt(),
  status: PaymentStatus.fromJson(json['status'] as String),
);

Map<String, dynamic> _$RefundOutToJson(RefundOut instance) => <String, dynamic>{
  'amount_paise': instance.amountPaise,
  'status': instance.status,
};
