// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'discount_rule_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

DiscountRuleOut _$DiscountRuleOutFromJson(Map<String, dynamic> json) =>
    DiscountRuleOut(
      active: json['active'] as bool,
      category: json['category'] == null
          ? null
          : ItemCategory.fromJson(json['category'] as String),
      createdAt: DateTime.parse(json['created_at'] as String),
      endTime: json['end_time'] as String,
      id: json['id'] as String,
      itemIds: (json['item_ids'] as List<dynamic>)
          .map((e) => e as String)
          .toList(),
      name: json['name'] as String,
      pct: (json['pct'] as num).toInt(),
      scope: DiscountScope.fromJson(json['scope'] as String),
      startTime: json['start_time'] as String,
    );

Map<String, dynamic> _$DiscountRuleOutToJson(DiscountRuleOut instance) =>
    <String, dynamic>{
      'active': instance.active,
      'category': instance.category,
      'created_at': instance.createdAt.toIso8601String(),
      'end_time': instance.endTime,
      'id': instance.id,
      'item_ids': instance.itemIds,
      'name': instance.name,
      'pct': instance.pct,
      'scope': instance.scope,
      'start_time': instance.startTime,
    };
