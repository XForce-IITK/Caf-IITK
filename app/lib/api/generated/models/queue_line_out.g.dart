// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'queue_line_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

QueueLineOut _$QueueLineOutFromJson(Map<String, dynamic> json) => QueueLineOut(
  itemId: json['item_id'] as String,
  name: json['name'] as String,
  qty: (json['qty'] as num).toInt(),
);

Map<String, dynamic> _$QueueLineOutToJson(QueueLineOut instance) =>
    <String, dynamic>{
      'item_id': instance.itemId,
      'name': instance.name,
      'qty': instance.qty,
    };
