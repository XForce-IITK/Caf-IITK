// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'discount_scope.dart';
import 'item_category.dart';

part 'discount_rule_create.g.dart';

/// FR-22. A slot is discounted when its start is in [start_time, end_time).
///
/// `category` is required for a CATEGORY rule and `item_ids` for an ITEMS rule;.
/// each is refused for any other scope.
@JsonSerializable()
class DiscountRuleCreate {
  const DiscountRuleCreate({
    required this.endTime,
    required this.name,
    required this.pct,
    required this.scope,
    required this.startTime,
    this.itemIds = const [],
    this.category,
  });

  factory DiscountRuleCreate.fromJson(Map<String, Object?> json) =>
      _$DiscountRuleCreateFromJson(json);

  final ItemCategory? category;
  @JsonKey(name: 'end_time')
  final String endTime;
  @JsonKey(name: 'item_ids')
  final List<String> itemIds;
  final String name;
  final int pct;
  final DiscountScope scope;
  @JsonKey(name: 'start_time')
  final String startTime;

  Map<String, Object?> toJson() => _$DiscountRuleCreateToJson(this);
}
