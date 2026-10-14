// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'queue_order_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

QueueOrderOut _$QueueOrderOutFromJson(Map<String, dynamic> json) =>
    QueueOrderOut(
      confirmedAt: DateTime.parse(json['confirmed_at'] as String),
      id: json['id'] as String,
      lines: (json['lines'] as List<dynamic>)
          .map((e) => QueueLineOut.fromJson(e as Map<String, dynamic>))
          .toList(),
      status: OrderStatus.fromJson(json['status'] as String),
    );

Map<String, dynamic> _$QueueOrderOutToJson(QueueOrderOut instance) =>
    <String, dynamic>{
      'confirmed_at': instance.confirmedAt.toIso8601String(),
      'id': instance.id,
      'lines': instance.lines,
      'status': instance.status,
    };
