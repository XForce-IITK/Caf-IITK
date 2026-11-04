// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'discount_scope.dart';
import 'item_category.dart';

part 'discount_rule_out.g.dart';

@JsonSerializable()
class DiscountRuleOut {
  const DiscountRuleOut({
    required this.active,
    required this.category,
    required this.createdAt,
    required this.endTime,
    required this.id,
    required this.itemIds,
    required this.name,
    required this.pct,
    required this.scope,
    required this.startTime,
  });

  factory DiscountRuleOut.fromJson(Map<String, Object?> json) =>
      _$DiscountRuleOutFromJson(json);

  final bool active;
  final ItemCategory? category;
  @JsonKey(name: 'created_at')
  final DateTime createdAt;
  @JsonKey(name: 'end_time')
  final String endTime;
  final String id;
  @JsonKey(name: 'item_ids')
  final List<String> itemIds;
  final String name;
  final int pct;
  final DiscountScope scope;
  @JsonKey(name: 'start_time')
  final String startTime;

  Map<String, Object?> toJson() => _$DiscountRuleOutToJson(this);
}
