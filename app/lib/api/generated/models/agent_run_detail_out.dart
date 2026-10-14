// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'agent_run_status.dart';
import 'agent_source.dart';
import 'agent_trigger.dart';
import 'proposal_out.dart';
import 'tool_call_out.dart';

part 'agent_run_detail_out.g.dart';

/// FR-63: the run, its report (FR-52), its proposals and its tool-call log (FR-62).
@JsonSerializable()
class AgentRunDetailOut {
  const AgentRunDetailOut({
    required this.finishedAt,
    required this.id,
    required this.proposals,
    required this.report,
    required this.source,
    required this.startedAt,
    required this.status,
    required this.toolCalls,
    required this.trigger,
  });

  factory AgentRunDetailOut.fromJson(Map<String, Object?> json) =>
      _$AgentRunDetailOutFromJson(json);

  @JsonKey(name: 'finished_at')
  final DateTime? finishedAt;
  final String id;
  final List<ProposalOut> proposals;
  final dynamic report;
  final AgentSource? source;
  @JsonKey(name: 'started_at')
  final DateTime startedAt;
  final AgentRunStatus status;
  @JsonKey(name: 'tool_calls')
  final List<ToolCallOut> toolCalls;
  final AgentTrigger trigger;

  Map<String, Object?> toJson() => _$AgentRunDetailOutToJson(this);
}
