// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

part 'slot_capacity_change.g.dart';

/// FR-18: one slot's new seat capacity, within the same bounds as the default.
@JsonSerializable()
class SlotCapacityChange {
  const SlotCapacityChange({required this.capacity});

  factory SlotCapacityChange.fromJson(Map<String, Object?> json) =>
      _$SlotCapacityChangeFromJson(json);

  final int capacity;

  Map<String, Object?> toJson() => _$SlotCapacityChangeToJson(this);
}
