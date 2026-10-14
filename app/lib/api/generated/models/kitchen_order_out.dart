// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'order_status.dart';

part 'kitchen_order_out.g.dart';

@JsonSerializable()
class KitchenOrderOut {
  const KitchenOrderOut({
    required this.id,
    required this.slotId,
    required this.status,
    required this.version,
  });

  factory KitchenOrderOut.fromJson(Map<String, Object?> json) =>
      _$KitchenOrderOutFromJson(json);

  final String id;
  @JsonKey(name: 'slot_id')
  final String slotId;
  final OrderStatus status;
  final int version;

  Map<String, Object?> toJson() => _$KitchenOrderOutToJson(this);
}
