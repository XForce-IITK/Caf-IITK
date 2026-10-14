// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'menu_item_out.dart';

part 'menu_out.g.dart';

@JsonSerializable()
class MenuOut {
  const MenuOut({required this.items, required this.serviceDate});

  factory MenuOut.fromJson(Map<String, Object?> json) =>
      _$MenuOutFromJson(json);

  final List<MenuItemOut> items;
  @JsonKey(name: 'service_date')
  final DateTime serviceDate;

  Map<String, Object?> toJson() => _$MenuOutToJson(this);
}
