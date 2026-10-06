// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'item_category.dart';

part 'item_create.g.dart';

@JsonSerializable()
class ItemCreate {
  const ItemCreate({
    required this.category,
    required this.name,
    required this.pricePaise,
    this.description = '',
  });

  factory ItemCreate.fromJson(Map<String, Object?> json) =>
      _$ItemCreateFromJson(json);

  final ItemCategory category;
  final String description;
  final String name;
  @JsonKey(name: 'price_paise')
  final int pricePaise;

  Map<String, Object?> toJson() => _$ItemCreateToJson(this);
}
