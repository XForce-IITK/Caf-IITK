// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'item_category.dart';

part 'item_update.g.dart';

/// FR-9: the fields the Administrator may edit; the name is fixed once onboarded.
@JsonSerializable()
class ItemUpdate {
  const ItemUpdate({this.category, this.description, this.pricePaise});

  factory ItemUpdate.fromJson(Map<String, Object?> json) =>
      _$ItemUpdateFromJson(json);

  final ItemCategory? category;
  final String? description;
  @JsonKey(name: 'price_paise')
  final int? pricePaise;

  Map<String, Object?> toJson() => _$ItemUpdateToJson(this);
}
