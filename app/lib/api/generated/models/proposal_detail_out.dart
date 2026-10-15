// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'agent_source.dart';
import 'proposal_status.dart';
import 'proposal_type.dart';

part 'proposal_detail_out.g.dart';

/// A proposal with its run (whose report holds the related forecast) and its decision.
@JsonSerializable()
class ProposalDetailOut {
  const ProposalDetailOut({
    required this.createdAt,
    required this.decidedAt,
    required this.decisionReason,
    required this.expiresAt,
    required this.id,
    required this.payload,
    required this.rationale,
    required this.runId,
    required this.source,
    required this.status,
    required this.targetDate,
    required this.targetSlotId,
    required this.type,
  });

  factory ProposalDetailOut.fromJson(Map<String, Object?> json) =>
      _$ProposalDetailOutFromJson(json);

  @JsonKey(name: 'created_at')
  final DateTime createdAt;
  @JsonKey(name: 'decided_at')
  final DateTime? decidedAt;
  @JsonKey(name: 'decision_reason')
  final String? decisionReason;
  @JsonKey(name: 'expires_at')
  final DateTime expiresAt;
  final String id;
  final dynamic payload;
  final String rationale;
  @JsonKey(name: 'run_id')
  final String runId;
  final AgentSource source;
  final ProposalStatus status;
  @JsonKey(name: 'target_date')
  final DateTime targetDate;
  @JsonKey(name: 'target_slot_id')
  final String? targetSlotId;
  final ProposalType type;

  Map<String, Object?> toJson() => _$ProposalDetailOutToJson(this);
}
