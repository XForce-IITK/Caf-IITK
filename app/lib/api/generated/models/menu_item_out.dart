// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'item_category.dart';
import 'not_orderable_reason.dart';

part 'menu_item_out.g.dart';

@JsonSerializable()
class MenuItemOut {
  const MenuItemOut({
    required this.availablePortions,
    required this.category,
    required this.description,
    required this.id,
    required this.name,
    required this.notOrderableReason,
    required this.orderable,
    required this.pricePaise,
  });
  
  factory MenuItemOut.fromJson(Map<String, Object?> json) => _$MenuItemOutFromJson(json);
  
  @JsonKey(name: 'available_portions')
  final int availablePortions;
  final ItemCategory category;
  final String description;
  final String id;
  final String name;
  @JsonKey(name: 'not_orderable_reason')
  final NotOrderableReason? notOrderableReason;
  final bool orderable;
  @JsonKey(name: 'price_paise')
  final int pricePaise;

  Map<String, Object?> toJson() => _$MenuItemOutToJson(this);
}
