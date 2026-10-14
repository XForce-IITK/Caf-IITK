// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'slot_list_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

SlotListOut _$SlotListOutFromJson(Map<String, dynamic> json) => SlotListOut(
  serviceDate: DateTime.parse(json['service_date'] as String),
  slots: (json['slots'] as List<dynamic>)
      .map((e) => SlotAvailabilityOut.fromJson(e as Map<String, dynamic>))
      .toList(),
);

Map<String, dynamic> _$SlotListOutToJson(SlotListOut instance) =>
    <String, dynamic>{
      'service_date': instance.serviceDate.toIso8601String(),
      'slots': instance.slots,
    };
