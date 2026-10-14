// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'kitchen_order_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

KitchenOrderOut _$KitchenOrderOutFromJson(Map<String, dynamic> json) =>
    KitchenOrderOut(
      id: json['id'] as String,
      slotId: json['slot_id'] as String,
      status: OrderStatus.fromJson(json['status'] as String),
      version: (json['version'] as num).toInt(),
    );

Map<String, dynamic> _$KitchenOrderOutToJson(KitchenOrderOut instance) =>
    <String, dynamic>{
      'id': instance.id,
      'slot_id': instance.slotId,
      'status': instance.status,
      'version': instance.version,
    };
