// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

part 'inventory_set.g.dart';

@JsonSerializable()
class InventorySet {
  const InventorySet({required this.total});

  factory InventorySet.fromJson(Map<String, Object?> json) =>
      _$InventorySetFromJson(json);

  final int total;

  Map<String, Object?> toJson() => _$InventorySetToJson(this);
}
