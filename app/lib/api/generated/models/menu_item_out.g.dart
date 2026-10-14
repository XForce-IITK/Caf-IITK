// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'menu_item_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

MenuItemOut _$MenuItemOutFromJson(Map<String, dynamic> json) => MenuItemOut(
  availablePortions: (json['available_portions'] as num).toInt(),
  category: ItemCategory.fromJson(json['category'] as String),
  description: json['description'] as String,
  id: json['id'] as String,
  name: json['name'] as String,
  notOrderableReason: json['not_orderable_reason'] == null
      ? null
      : NotOrderableReason.fromJson(json['not_orderable_reason'] as String),
  orderable: json['orderable'] as bool,
  pricePaise: (json['price_paise'] as num).toInt(),
);

Map<String, dynamic> _$MenuItemOutToJson(MenuItemOut instance) =>
    <String, dynamic>{
      'available_portions': instance.availablePortions,
      'category': instance.category,
      'description': instance.description,
      'id': instance.id,
      'name': instance.name,
      'not_orderable_reason': instance.notOrderableReason,
      'orderable': instance.orderable,
      'price_paise': instance.pricePaise,
    };
