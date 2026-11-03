// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'slot_utilisation_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

SlotUtilisationOut _$SlotUtilisationOutFromJson(Map<String, dynamic> json) =>
    SlotUtilisationOut(
      booked: (json['booked'] as num).toInt(),
      capacity: (json['capacity'] as num).toInt(),
      endsAt: DateTime.parse(json['ends_at'] as String),
      slotId: json['slot_id'] as String,
      startsAt: DateTime.parse(json['starts_at'] as String),
    );

Map<String, dynamic> _$SlotUtilisationOutToJson(SlotUtilisationOut instance) =>
    <String, dynamic>{
      'booked': instance.booked,
      'capacity': instance.capacity,
      'ends_at': instance.endsAt.toIso8601String(),
      'slot_id': instance.slotId,
      'starts_at': instance.startsAt.toIso8601String(),
    };
