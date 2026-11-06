// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'discount_rule_create.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

DiscountRuleCreate _$DiscountRuleCreateFromJson(Map<String, dynamic> json) =>
    DiscountRuleCreate(
      endTime: json['end_time'] as String,
      name: json['name'] as String,
      pct: (json['pct'] as num).toInt(),
      scope: DiscountScope.fromJson(json['scope'] as String),
      startTime: json['start_time'] as String,
      itemIds:
          (json['item_ids'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          const [],
      category: json['category'] == null
          ? null
          : ItemCategory.fromJson(json['category'] as String),
    );

Map<String, dynamic> _$DiscountRuleCreateToJson(DiscountRuleCreate instance) =>
    <String, dynamic>{
      'category': instance.category,
      'end_time': instance.endTime,
      'item_ids': instance.itemIds,
      'name': instance.name,
      'pct': instance.pct,
      'scope': instance.scope,
      'start_time': instance.startTime,
    };
