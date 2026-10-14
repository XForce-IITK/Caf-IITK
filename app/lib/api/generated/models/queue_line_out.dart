// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

part 'queue_line_out.g.dart';

@JsonSerializable()
class QueueLineOut {
  const QueueLineOut({
    required this.itemId,
    required this.name,
    required this.qty,
  });

  factory QueueLineOut.fromJson(Map<String, Object?> json) =>
      _$QueueLineOutFromJson(json);

  @JsonKey(name: 'item_id')
  final String itemId;
  final String name;
  final int qty;

  Map<String, Object?> toJson() => _$QueueLineOutToJson(this);
}
