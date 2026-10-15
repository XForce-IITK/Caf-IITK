// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'item_create.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

ItemCreate _$ItemCreateFromJson(Map<String, dynamic> json) => ItemCreate(
  category: ItemCategory.fromJson(json['category'] as String),
  name: json['name'] as String,
  pricePaise: (json['price_paise'] as num).toInt(),
  description: json['description'] as String? ?? '',
);

Map<String, dynamic> _$ItemCreateToJson(ItemCreate instance) =>
    <String, dynamic>{
      'category': instance.category,
      'description': instance.description,
      'name': instance.name,
      'price_paise': instance.pricePaise,
    };
