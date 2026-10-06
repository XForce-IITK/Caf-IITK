// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'slot_availability_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

SlotAvailabilityOut _$SlotAvailabilityOutFromJson(Map<String, dynamic> json) =>
    SlotAvailabilityOut(
      bookable: json['bookable'] as bool,
      endsAt: DateTime.parse(json['ends_at'] as String),
      id: json['id'] as String,
      notBookableReason: json['not_bookable_reason'] == null
          ? null
          : NotBookableReason.fromJson(json['not_bookable_reason'] as String),
      remainingSeats: (json['remaining_seats'] as num).toInt(),
      startsAt: DateTime.parse(json['starts_at'] as String),
    );

Map<String, dynamic> _$SlotAvailabilityOutToJson(
  SlotAvailabilityOut instance,
) => <String, dynamic>{
  'bookable': instance.bookable,
  'ends_at': instance.endsAt.toIso8601String(),
  'id': instance.id,
  'not_bookable_reason': instance.notBookableReason,
  'remaining_seats': instance.remainingSeats,
  'starts_at': instance.startsAt.toIso8601String(),
};
