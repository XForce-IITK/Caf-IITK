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
      refunds: (json['refunds'] as List<dynamic>)
          .map((e) => OrderRefundOut.fromJson(e as Map<String, dynamic>))
          .toList(),
      slotId: json['slot_id'] as String,
      snapshots: (json['snapshots'] as List<dynamic>)
          .map((e) => SnapshotOut.fromJson(e as Map<String, dynamic>))
          .toList(),
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
      'refunds': instance.refunds,
      'slot_id': instance.slotId,
      'snapshots': instance.snapshots,
      'status': instance.status,
      'subsidy_applied': instance.subsidyApplied,
      'version': instance.version,
    };
