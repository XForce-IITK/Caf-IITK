// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'slot_out.dart';

part 'service_day_out.g.dart';

@JsonSerializable()
class ServiceDayOut {
  const ServiceDayOut({
    required this.defaultCapacity,
    required this.serviceDate,
    required this.slotLenMin,
    required this.slots,
    required this.windowEnd,
    required this.windowStart,
  });

  factory ServiceDayOut.fromJson(Map<String, Object?> json) =>
      _$ServiceDayOutFromJson(json);

  @JsonKey(name: 'default_capacity')
  final int defaultCapacity;
  @JsonKey(name: 'service_date')
  final DateTime serviceDate;
  @JsonKey(name: 'slot_len_min')
  final int slotLenMin;
  final List<SlotOut> slots;
  @JsonKey(name: 'window_end')
  final String windowEnd;
  @JsonKey(name: 'window_start')
  final String windowStart;

  Map<String, Object?> toJson() => _$ServiceDayOutToJson(this);
}
