// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'proposal_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

ProposalOut _$ProposalOutFromJson(Map<String, dynamic> json) => ProposalOut(
  expiresAt: DateTime.parse(json['expires_at'] as String),
  id: json['id'] as String,
  payload: json['payload'],
  rationale: json['rationale'] as String,
  source: AgentSource.fromJson(json['source'] as String),
  status: ProposalStatus.fromJson(json['status'] as String),
  targetDate: DateTime.parse(json['target_date'] as String),
  targetSlotId: json['target_slot_id'] as String?,
  type: ProposalType.fromJson(json['type'] as String),
);

Map<String, dynamic> _$ProposalOutToJson(ProposalOut instance) =>
    <String, dynamic>{
      'expires_at': instance.expiresAt.toIso8601String(),
      'id': instance.id,
      'payload': instance.payload,
      'rationale': instance.rationale,
      'source': instance.source,
      'status': instance.status,
      'target_date': instance.targetDate.toIso8601String(),
      'target_slot_id': instance.targetSlotId,
      'type': instance.type,
    };
