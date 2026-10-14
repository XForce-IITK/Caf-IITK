// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'agent_run_detail_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

AgentRunDetailOut _$AgentRunDetailOutFromJson(Map<String, dynamic> json) =>
    AgentRunDetailOut(
      finishedAt: json['finished_at'] == null
          ? null
          : DateTime.parse(json['finished_at'] as String),
      id: json['id'] as String,
      proposals: (json['proposals'] as List<dynamic>)
          .map((e) => ProposalOut.fromJson(e as Map<String, dynamic>))
          .toList(),
      report: json['report'],
      source: json['source'] == null
          ? null
          : AgentSource.fromJson(json['source'] as String),
      startedAt: DateTime.parse(json['started_at'] as String),
      status: AgentRunStatus.fromJson(json['status'] as String),
      toolCalls: (json['tool_calls'] as List<dynamic>)
          .map((e) => ToolCallOut.fromJson(e as Map<String, dynamic>))
          .toList(),
      trigger: AgentTrigger.fromJson(json['trigger'] as String),
    );

Map<String, dynamic> _$AgentRunDetailOutToJson(AgentRunDetailOut instance) =>
    <String, dynamic>{
      'finished_at': instance.finishedAt?.toIso8601String(),
      'id': instance.id,
      'proposals': instance.proposals,
      'report': instance.report,
      'source': instance.source,
      'started_at': instance.startedAt.toIso8601String(),
      'status': instance.status,
      'tool_calls': instance.toolCalls,
      'trigger': instance.trigger,
    };
