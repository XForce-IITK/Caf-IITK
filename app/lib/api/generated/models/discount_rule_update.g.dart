// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'discount_rule_update.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

DiscountRuleUpdate _$DiscountRuleUpdateFromJson(Map<String, dynamic> json) =>
    DiscountRuleUpdate(
      active: json['active'] as bool?,
      category: json['category'] == null
          ? null
          : ItemCategory.fromJson(json['category'] as String),
      endTime: json['end_time'] as String?,
      itemIds: (json['item_ids'] as List<dynamic>?)
          ?.map((e) => e as String)
          .toList(),
      name: json['name'] as String?,
      pct: (json['pct'] as num?)?.toInt(),
      scope: json['scope'] == null
          ? null
          : DiscountScope.fromJson(json['scope'] as String),
      startTime: json['start_time'] as String?,
    );

Map<String, dynamic> _$DiscountRuleUpdateToJson(DiscountRuleUpdate instance) =>
    <String, dynamic>{
      'active': instance.active,
      'category': instance.category,
      'end_time': instance.endTime,
      'item_ids': instance.itemIds,
      'name': instance.name,
      'pct': instance.pct,
      'scope': instance.scope,
      'start_time': instance.startTime,
    };
