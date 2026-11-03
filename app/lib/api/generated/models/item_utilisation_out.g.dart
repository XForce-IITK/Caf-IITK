// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'item_utilisation_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

ItemUtilisationOut _$ItemUtilisationOutFromJson(Map<String, dynamic> json) =>
    ItemUtilisationOut(
      allocated: (json['allocated'] as num).toInt(),
      available: (json['available'] as num).toInt(),
      itemId: json['item_id'] as String,
      name: json['name'] as String,
      total: (json['total'] as num).toInt(),
    );

Map<String, dynamic> _$ItemUtilisationOutToJson(ItemUtilisationOut instance) =>
    <String, dynamic>{
      'allocated': instance.allocated,
      'available': instance.available,
      'item_id': instance.itemId,
      'name': instance.name,
      'total': instance.total,
    };
