// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'audit_entry_out.dart';

part 'audit_page_out.g.dart';

@JsonSerializable()
class AuditPageOut {
  const AuditPageOut({required this.entries, required this.nextBeforeId});

  factory AuditPageOut.fromJson(Map<String, Object?> json) =>
      _$AuditPageOutFromJson(json);

  final List<AuditEntryOut> entries;
  @JsonKey(name: 'next_before_id')
  final int? nextBeforeId;

  Map<String, Object?> toJson() => _$AuditPageOutToJson(this);
}
