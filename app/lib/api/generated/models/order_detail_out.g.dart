// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'order_detail_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

OrderDetailOut _$OrderDetailOutFromJson(Map<String, dynamic> json) =>
    OrderDetailOut(
      createdAt: DateTime.parse(json['created_at'] as String),
      history: (json['history'] as List<dynamic>)
          .map((e) => TransitionOut.fromJson(e as Map<String, dynamic>))
          .toList(),
      id: json['id'] as String,
      paidPaise: (json['paid_paise'] as num).toInt(),
      price: QuoteOut.fromJson(json['price'] as Map<String, dynamic>),
      slotId: json['slot_id'] as String,
      status: OrderStatus.fromJson(json['status'] as String),
      subsidyApplied: json['subsidy_applied'] as bool,
      version: (json['version'] as num).toInt(),
    );

Map<String, dynamic> _$OrderDetailOutToJson(OrderDetailOut instance) =>
    <String, dynamic>{
      'created_at': instance.createdAt.toIso8601String(),
      'history': instance.history,
      'id': instance.id,
      'paid_paise': instance.paidPaise,
      'price': instance.price,
      'slot_id': instance.slotId,
      'status': instance.status,
      'subsidy_applied': instance.subsidyApplied,
      'version': instance.version,
    };
