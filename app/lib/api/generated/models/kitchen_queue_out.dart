// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'slot_queue_out.dart';

part 'kitchen_queue_out.g.dart';

/// FR-42: the current slot, then the next one; fewer near the end of service.
@JsonSerializable()
class KitchenQueueOut {
  const KitchenQueueOut({required this.earlierSlots, required this.slots});

  factory KitchenQueueOut.fromJson(Map<String, Object?> json) =>
      _$KitchenQueueOutFromJson(json);

  @JsonKey(name: 'earlier_slots')
  final List<SlotQueueOut> earlierSlots;
  final List<SlotQueueOut> slots;

  Map<String, Object?> toJson() => _$KitchenQueueOutToJson(this);
}
