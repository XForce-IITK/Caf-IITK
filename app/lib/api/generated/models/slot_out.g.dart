// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'slot_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

SlotOut _$SlotOutFromJson(Map<String, dynamic> json) => SlotOut(
  booked: (json['booked'] as num).toInt(),
  capacity: (json['capacity'] as num).toInt(),
  endsAt: DateTime.parse(json['ends_at'] as String),
  id: json['id'] as String,
  startsAt: DateTime.parse(json['starts_at'] as String),
);

Map<String, dynamic> _$SlotOutToJson(SlotOut instance) => <String, dynamic>{
  'booked': instance.booked,
  'capacity': instance.capacity,
  'ends_at': instance.endsAt.toIso8601String(),
  'id': instance.id,
  'starts_at': instance.startsAt.toIso8601String(),
};
