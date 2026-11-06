// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'item_update.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

ItemUpdate _$ItemUpdateFromJson(Map<String, dynamic> json) => ItemUpdate(
  category: json['category'] == null
      ? null
      : ItemCategory.fromJson(json['category'] as String),
  description: json['description'] as String?,
  pricePaise: (json['price_paise'] as num?)?.toInt(),
);

Map<String, dynamic> _$ItemUpdateToJson(ItemUpdate instance) =>
    <String, dynamic>{
      'category': instance.category,
      'description': instance.description,
      'price_paise': instance.pricePaise,
    };
