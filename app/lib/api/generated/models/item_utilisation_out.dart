// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

part 'item_utilisation_out.g.dart';

@JsonSerializable()
class ItemUtilisationOut {
  const ItemUtilisationOut({
    required this.allocated,
    required this.available,
    required this.itemId,
    required this.name,
    required this.total,
  });

  factory ItemUtilisationOut.fromJson(Map<String, Object?> json) =>
      _$ItemUtilisationOutFromJson(json);

  final int allocated;
  final int available;
  @JsonKey(name: 'item_id')
  final String itemId;
  final String name;
  final int total;

  Map<String, Object?> toJson() => _$ItemUtilisationOutToJson(this);
}
