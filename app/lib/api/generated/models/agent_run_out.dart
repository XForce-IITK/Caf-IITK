// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'agent_run_status.dart';
import 'agent_source.dart';
import 'agent_trigger.dart';

part 'agent_run_out.g.dart';

@JsonSerializable()
class AgentRunOut {
  const AgentRunOut({
    required this.finishedAt,
    required this.id,
    required this.source,
    required this.startedAt,
    required this.status,
    required this.trigger,
  });

  factory AgentRunOut.fromJson(Map<String, Object?> json) =>
      _$AgentRunOutFromJson(json);

  @JsonKey(name: 'finished_at')
  final DateTime? finishedAt;
  final String id;
  final AgentSource? source;
  @JsonKey(name: 'started_at')
  final DateTime startedAt;
  final AgentRunStatus status;
  final AgentTrigger trigger;

  Map<String, Object?> toJson() => _$AgentRunOutToJson(this);
}
