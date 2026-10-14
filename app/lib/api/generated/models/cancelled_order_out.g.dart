// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'cancelled_order_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

CancelledOrderOut _$CancelledOrderOutFromJson(Map<String, dynamic> json) =>
    CancelledOrderOut(
      createdAt: DateTime.parse(json['created_at'] as String),
      id: json['id'] as String,
      paidPaise: (json['paid_paise'] as num).toInt(),
      price: QuoteOut.fromJson(json['price'] as Map<String, dynamic>),
      refund: RefundOut.fromJson(json['refund'] as Map<String, dynamic>),
      slotId: json['slot_id'] as String,
      status: OrderStatus.fromJson(json['status'] as String),
      subsidyApplied: json['subsidy_applied'] as bool,
      version: (json['version'] as num).toInt(),
    );

Map<String, dynamic> _$CancelledOrderOutToJson(CancelledOrderOut instance) =>
    <String, dynamic>{
      'created_at': instance.createdAt.toIso8601String(),
      'id': instance.id,
      'paid_paise': instance.paidPaise,
      'price': instance.price,
      'refund': instance.refund,
      'slot_id': instance.slotId,
      'status': instance.status,
      'subsidy_applied': instance.subsidyApplied,
      'version': instance.version,
    };
