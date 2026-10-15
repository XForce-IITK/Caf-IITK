// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'service_day_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

ServiceDayOut _$ServiceDayOutFromJson(Map<String, dynamic> json) =>
    ServiceDayOut(
      defaultCapacity: (json['default_capacity'] as num).toInt(),
      serviceDate: DateTime.parse(json['service_date'] as String),
      slotLenMin: (json['slot_len_min'] as num).toInt(),
      slots: (json['slots'] as List<dynamic>)
          .map((e) => SlotOut.fromJson(e as Map<String, dynamic>))
          .toList(),
      windowEnd: json['window_end'] as String,
      windowStart: json['window_start'] as String,
    );

Map<String, dynamic> _$ServiceDayOutToJson(ServiceDayOut instance) =>
    <String, dynamic>{
      'default_capacity': instance.defaultCapacity,
      'service_date': instance.serviceDate.toIso8601String(),
      'slot_len_min': instance.slotLenMin,
      'slots': instance.slots,
      'window_end': instance.windowEnd,
      'window_start': instance.windowStart,
    };
