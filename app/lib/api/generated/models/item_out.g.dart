// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'item_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

ItemOut _$ItemOutFromJson(Map<String, dynamic> json) => ItemOut(
  category: ItemCategory.fromJson(json['category'] as String),
  description: json['description'] as String,
  id: json['id'] as String,
  name: json['name'] as String,
  pricePaise: (json['price_paise'] as num).toInt(),
  status: ItemStatus.fromJson(json['status'] as String),
  unavailable: json['unavailable'] as bool,
);

Map<String, dynamic> _$ItemOutToJson(ItemOut instance) => <String, dynamic>{
  'category': instance.category,
  'description': instance.description,
  'id': instance.id,
  'name': instance.name,
  'price_paise': instance.pricePaise,
  'status': instance.status,
  'unavailable': instance.unavailable,
};
