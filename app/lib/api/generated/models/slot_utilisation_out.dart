// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

part 'slot_utilisation_out.g.dart';

@JsonSerializable()
class SlotUtilisationOut {
  const SlotUtilisationOut({
    required this.booked,
    required this.capacity,
    required this.endsAt,
    required this.slotId,
    required this.startsAt,
  });

  factory SlotUtilisationOut.fromJson(Map<String, Object?> json) =>
      _$SlotUtilisationOutFromJson(json);

  final int booked;
  final int capacity;
  @JsonKey(name: 'ends_at')
  final DateTime endsAt;
  @JsonKey(name: 'slot_id')
  final String slotId;
  @JsonKey(name: 'starts_at')
  final DateTime startsAt;

  Map<String, Object?> toJson() => _$SlotUtilisationOutToJson(this);
}
