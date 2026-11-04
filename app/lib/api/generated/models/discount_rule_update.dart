// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'discount_scope.dart';
import 'item_category.dart';

part 'discount_rule_update.g.dart';

/// FR-22: change any of a rule's fields, or deactivate (and reactivate) it.
///
/// Changing `scope` clears `category` and `item_ids` unless they are given too.
@JsonSerializable()
class DiscountRuleUpdate {
  const DiscountRuleUpdate({
    this.active,
    this.category,
    this.endTime,
    this.itemIds,
    this.name,
    this.pct,
    this.scope,
    this.startTime,
  });

  factory DiscountRuleUpdate.fromJson(Map<String, Object?> json) =>
      _$DiscountRuleUpdateFromJson(json);

  final bool? active;
  final ItemCategory? category;
  @JsonKey(name: 'end_time')
  final String? endTime;
  @JsonKey(name: 'item_ids')
  final List<String>? itemIds;
  final String? name;
  final int? pct;
  final DiscountScope? scope;
  @JsonKey(name: 'start_time')
  final String? startTime;

  Map<String, Object?> toJson() => _$DiscountRuleUpdateToJson(this);
}
