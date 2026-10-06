// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'menu_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

MenuOut _$MenuOutFromJson(Map<String, dynamic> json) => MenuOut(
  items: (json['items'] as List<dynamic>)
      .map((e) => MenuItemOut.fromJson(e as Map<String, dynamic>))
      .toList(),
  serviceDate: DateTime.parse(json['service_date'] as String),
);

Map<String, dynamic> _$MenuOutToJson(MenuOut instance) => <String, dynamic>{
  'items': instance.items,
  'service_date': instance.serviceDate.toIso8601String(),
};
