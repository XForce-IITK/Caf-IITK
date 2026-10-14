// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'agent_run_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

AgentRunOut _$AgentRunOutFromJson(Map<String, dynamic> json) => AgentRunOut(
  finishedAt: json['finished_at'] == null
      ? null
      : DateTime.parse(json['finished_at'] as String),
  id: json['id'] as String,
  source: json['source'] == null
      ? null
      : AgentSource.fromJson(json['source'] as String),
  startedAt: DateTime.parse(json['started_at'] as String),
  status: AgentRunStatus.fromJson(json['status'] as String),
  trigger: AgentTrigger.fromJson(json['trigger'] as String),
);

Map<String, dynamic> _$AgentRunOutToJson(AgentRunOut instance) =>
    <String, dynamic>{
      'finished_at': instance.finishedAt?.toIso8601String(),
      'id': instance.id,
      'source': instance.source,
      'started_at': instance.startedAt.toIso8601String(),
      'status': instance.status,
      'trigger': instance.trigger,
    };
