// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

part 'slot_out.g.dart';

@JsonSerializable()
class SlotOut {
  const SlotOut({
    required this.booked,
    required this.capacity,
    required this.endsAt,
    required this.id,
    required this.startsAt,
  });

  factory SlotOut.fromJson(Map<String, Object?> json) =>
      _$SlotOutFromJson(json);

  final int booked;
  final int capacity;
  @JsonKey(name: 'ends_at')
  final DateTime endsAt;
  final String id;
  @JsonKey(name: 'starts_at')
  final DateTime startsAt;

  Map<String, Object?> toJson() => _$SlotOutToJson(this);
}
