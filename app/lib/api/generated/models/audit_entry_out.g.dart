// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'audit_entry_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

AuditEntryOut _$AuditEntryOutFromJson(Map<String, dynamic> json) =>
    AuditEntryOut(
      action: json['action'] as String,
      actorId: json['actor_id'] as String?,
      actorRole: json['actor_role'] as String?,
      after: json['after'],
      at: DateTime.parse(json['at'] as String),
      before: json['before'],
      correlationId: json['correlation_id'] as String?,
      entityId: json['entity_id'] as String?,
      entityType: json['entity_type'] as String,
      id: (json['id'] as num).toInt(),
    );

Map<String, dynamic> _$AuditEntryOutToJson(AuditEntryOut instance) =>
    <String, dynamic>{
      'action': instance.action,
      'actor_id': instance.actorId,
      'actor_role': instance.actorRole,
      'after': instance.after,
      'at': instance.at.toIso8601String(),
      'before': instance.before,
      'correlation_id': instance.correlationId,
      'entity_id': instance.entityId,
      'entity_type': instance.entityType,
      'id': instance.id,
    };
