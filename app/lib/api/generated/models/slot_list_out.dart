// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'slot_availability_out.dart';

part 'slot_list_out.g.dart';

@JsonSerializable()
class SlotListOut {
  const SlotListOut({required this.serviceDate, required this.slots});

  factory SlotListOut.fromJson(Map<String, Object?> json) =>
      _$SlotListOutFromJson(json);

  @JsonKey(name: 'service_date')
  final DateTime serviceDate;
  final List<SlotAvailabilityOut> slots;

  Map<String, Object?> toJson() => _$SlotListOutToJson(this);
}
