// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

part 'audit_entry_out.g.dart';

/// One audit entry (FR-47), with any secret-looking value redacted (FR-49).
@JsonSerializable()
class AuditEntryOut {
  const AuditEntryOut({
    required this.action,
    required this.actorId,
    required this.actorRole,
    required this.after,
    required this.at,
    required this.before,
    required this.correlationId,
    required this.entityId,
    required this.entityType,
    required this.id,
  });

  factory AuditEntryOut.fromJson(Map<String, Object?> json) =>
      _$AuditEntryOutFromJson(json);

  final String action;
  @JsonKey(name: 'actor_id')
  final String? actorId;
  @JsonKey(name: 'actor_role')
  final String? actorRole;
  final dynamic after;
  final DateTime at;
  final dynamic before;
  @JsonKey(name: 'correlation_id')
  final String? correlationId;
  @JsonKey(name: 'entity_id')
  final String? entityId;
  @JsonKey(name: 'entity_type')
  final String entityType;
  final int id;

  Map<String, Object?> toJson() => _$AuditEntryOutToJson(this);
}
