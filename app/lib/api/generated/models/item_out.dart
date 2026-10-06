// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'item_category.dart';
import 'item_status.dart';

part 'item_out.g.dart';

@JsonSerializable()
class ItemOut {
  const ItemOut({
    required this.category,
    required this.description,
    required this.id,
    required this.name,
    required this.pricePaise,
    required this.status,
    required this.unavailable,
  });
  
  factory ItemOut.fromJson(Map<String, Object?> json) => _$ItemOutFromJson(json);
  
  final ItemCategory category;
  final String description;
  final String id;
  final String name;
  @JsonKey(name: 'price_paise')
  final int pricePaise;
  final ItemStatus status;
  final bool unavailable;

  Map<String, Object?> toJson() => _$ItemOutToJson(this);
}
