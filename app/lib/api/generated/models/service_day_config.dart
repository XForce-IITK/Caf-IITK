// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

part 'service_day_config.g.dart';

/// FR-17. Times are IST wall-clock; the window must lie within one day.
@JsonSerializable()
class ServiceDayConfig {
  const ServiceDayConfig({
    required this.defaultCapacity,
    required this.windowEnd,
    required this.windowStart,
    this.slotLenMin,
  });

  factory ServiceDayConfig.fromJson(Map<String, Object?> json) =>
      _$ServiceDayConfigFromJson(json);

  @JsonKey(name: 'default_capacity')
  final int defaultCapacity;
  @JsonKey(name: 'slot_len_min')
  final int? slotLenMin;
  @JsonKey(name: 'window_end')
  final String windowEnd;
  @JsonKey(name: 'window_start')
  final String windowStart;

  Map<String, Object?> toJson() => _$ServiceDayConfigToJson(this);
}
