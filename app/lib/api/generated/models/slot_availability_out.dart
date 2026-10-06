// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'not_bookable_reason.dart';

part 'slot_availability_out.g.dart';

@JsonSerializable()
class SlotAvailabilityOut {
  const SlotAvailabilityOut({
    required this.bookable,
    required this.endsAt,
    required this.id,
    required this.notBookableReason,
    required this.remainingSeats,
    required this.startsAt,
  });
  
  factory SlotAvailabilityOut.fromJson(Map<String, Object?> json) => _$SlotAvailabilityOutFromJson(json);
  
  final bool bookable;
  @JsonKey(name: 'ends_at')
  final DateTime endsAt;
  final String id;
  @JsonKey(name: 'not_bookable_reason')
  final NotBookableReason? notBookableReason;
  @JsonKey(name: 'remaining_seats')
  final int remainingSeats;
  @JsonKey(name: 'starts_at')
  final DateTime startsAt;

  Map<String, Object?> toJson() => _$SlotAvailabilityOutToJson(this);
}
