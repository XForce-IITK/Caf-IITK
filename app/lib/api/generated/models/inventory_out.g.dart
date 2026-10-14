// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'inventory_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

InventoryOut _$InventoryOutFromJson(Map<String, dynamic> json) => InventoryOut(
  allocated: (json['allocated'] as num).toInt(),
  available: (json['available'] as num).toInt(),
  itemId: json['item_id'] as String,
  serviceDate: DateTime.parse(json['service_date'] as String),
  total: (json['total'] as num).toInt(),
);

Map<String, dynamic> _$InventoryOutToJson(InventoryOut instance) =>
    <String, dynamic>{
      'allocated': instance.allocated,
      'available': instance.available,
      'item_id': instance.itemId,
      'service_date': instance.serviceDate.toIso8601String(),
      'total': instance.total,
    };
