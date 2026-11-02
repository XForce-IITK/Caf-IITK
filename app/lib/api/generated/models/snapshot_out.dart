// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'quote_out.dart';

part 'snapshot_out.g.dart';

/// One immutable price snapshot version (FR-27).
@JsonSerializable()
class SnapshotOut {
  const SnapshotOut({
    required this.price,
    required this.pricedAt,
    required this.version,
  });

  factory SnapshotOut.fromJson(Map<String, Object?> json) =>
      _$SnapshotOutFromJson(json);

  final QuoteOut price;
  @JsonKey(name: 'priced_at')
  final DateTime pricedAt;
  final int version;

  Map<String, Object?> toJson() => _$SnapshotOutToJson(this);
}
