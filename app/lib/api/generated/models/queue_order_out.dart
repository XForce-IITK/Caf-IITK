// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'order_status.dart';
import 'queue_line_out.dart';

part 'queue_order_out.g.dart';

@JsonSerializable()
class QueueOrderOut {
  const QueueOrderOut({
    required this.confirmedAt,
    required this.id,
    required this.lines,
    required this.status,
  });

  factory QueueOrderOut.fromJson(Map<String, Object?> json) =>
      _$QueueOrderOutFromJson(json);

  @JsonKey(name: 'confirmed_at')
  final DateTime confirmedAt;
  final String id;
  final List<QueueLineOut> lines;
  final OrderStatus status;

  Map<String, Object?> toJson() => _$QueueOrderOutToJson(this);
}
