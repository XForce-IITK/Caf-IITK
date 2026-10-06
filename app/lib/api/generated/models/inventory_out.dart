// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

part 'inventory_out.g.dart';

@JsonSerializable()
class InventoryOut {
  const InventoryOut({
    required this.allocated,
    required this.available,
    required this.itemId,
    required this.serviceDate,
    required this.total,
  });

  factory InventoryOut.fromJson(Map<String, Object?> json) =>
      _$InventoryOutFromJson(json);

  final int allocated;
  final int available;
  @JsonKey(name: 'item_id')
  final String itemId;
  @JsonKey(name: 'service_date')
  final DateTime serviceDate;
  final int total;

  Map<String, Object?> toJson() => _$InventoryOutToJson(this);
}
