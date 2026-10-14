// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'proposal_detail_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

ProposalDetailOut _$ProposalDetailOutFromJson(Map<String, dynamic> json) =>
    ProposalDetailOut(
      createdAt: DateTime.parse(json['created_at'] as String),
      decidedAt: json['decided_at'] == null
          ? null
          : DateTime.parse(json['decided_at'] as String),
      decisionReason: json['decision_reason'] as String?,
      expiresAt: DateTime.parse(json['expires_at'] as String),
      id: json['id'] as String,
      payload: json['payload'],
      rationale: json['rationale'] as String,
      runId: json['run_id'] as String,
      source: AgentSource.fromJson(json['source'] as String),
      status: ProposalStatus.fromJson(json['status'] as String),
      targetDate: DateTime.parse(json['target_date'] as String),
      targetSlotId: json['target_slot_id'] as String?,
      type: ProposalType.fromJson(json['type'] as String),
    );

Map<String, dynamic> _$ProposalDetailOutToJson(ProposalDetailOut instance) =>
    <String, dynamic>{
      'created_at': instance.createdAt.toIso8601String(),
      'decided_at': instance.decidedAt?.toIso8601String(),
      'decision_reason': instance.decisionReason,
      'expires_at': instance.expiresAt.toIso8601String(),
      'id': instance.id,
      'payload': instance.payload,
      'rationale': instance.rationale,
      'run_id': instance.runId,
      'source': instance.source,
      'status': instance.status,
      'target_date': instance.targetDate.toIso8601String(),
      'target_slot_id': instance.targetSlotId,
      'type': instance.type,
    };
