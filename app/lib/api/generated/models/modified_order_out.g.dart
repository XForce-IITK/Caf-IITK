// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'modified_order_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

ModifiedOrderOut _$ModifiedOrderOutFromJson(Map<String, dynamic> json) =>
    ModifiedOrderOut(
      createdAt: DateTime.parse(json['created_at'] as String),
      differencePaise: (json['difference_paise'] as num).toInt(),
      id: json['id'] as String,
      paidPaise: (json['paid_paise'] as num).toInt(),
      price: QuoteOut.fromJson(json['price'] as Map<String, dynamic>),
      refund: json['refund'] == null
          ? null
          : RefundOut.fromJson(json['refund'] as Map<String, dynamic>),
      slotId: json['slot_id'] as String,
      status: OrderStatus.fromJson(json['status'] as String),
      subsidyApplied: json['subsidy_applied'] as bool,
      version: (json['version'] as num).toInt(),
    );

Map<String, dynamic> _$ModifiedOrderOutToJson(ModifiedOrderOut instance) =>
    <String, dynamic>{
      'created_at': instance.createdAt.toIso8601String(),
      'difference_paise': instance.differencePaise,
      'id': instance.id,
      'paid_paise': instance.paidPaise,
      'price': instance.price,
      'refund': instance.refund,
      'slot_id': instance.slotId,
      'status': instance.status,
      'subsidy_applied': instance.subsidyApplied,
      'version': instance.version,
    };
