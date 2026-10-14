// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'agent_source.dart';
import 'proposal_status.dart';
import 'proposal_type.dart';

part 'proposal_out.g.dart';

@JsonSerializable()
class ProposalOut {
  const ProposalOut({
    required this.expiresAt,
    required this.id,
    required this.payload,
    required this.rationale,
    required this.source,
    required this.status,
    required this.targetDate,
    required this.targetSlotId,
    required this.type,
  });

  factory ProposalOut.fromJson(Map<String, Object?> json) =>
      _$ProposalOutFromJson(json);

  @JsonKey(name: 'expires_at')
  final DateTime expiresAt;
  final String id;
  final dynamic payload;
  final String rationale;
  final AgentSource source;
  final ProposalStatus status;
  @JsonKey(name: 'target_date')
  final DateTime targetDate;
  @JsonKey(name: 'target_slot_id')
  final String? targetSlotId;
  final ProposalType type;

  Map<String, Object?> toJson() => _$ProposalOutToJson(this);
}
