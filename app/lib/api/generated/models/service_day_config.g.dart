// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'service_day_config.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

ServiceDayConfig _$ServiceDayConfigFromJson(Map<String, dynamic> json) =>
    ServiceDayConfig(
      defaultCapacity: (json['default_capacity'] as num).toInt(),
      windowEnd: json['window_end'] as String,
      windowStart: json['window_start'] as String,
      slotLenMin: (json['slot_len_min'] as num?)?.toInt(),
    );

Map<String, dynamic> _$ServiceDayConfigToJson(ServiceDayConfig instance) =>
    <String, dynamic>{
      'default_capacity': instance.defaultCapacity,
      'slot_len_min': instance.slotLenMin,
      'window_end': instance.windowEnd,
      'window_start': instance.windowStart,
    };
