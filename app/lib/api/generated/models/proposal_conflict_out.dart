// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'proposal_detail_out.dart';

part 'proposal_conflict_out.g.dart';

/// 409: the proposal was not applied; `proposal.status` says why.
@JsonSerializable()
class ProposalConflictOut {
  const ProposalConflictOut({required this.message, required this.proposal});

  factory ProposalConflictOut.fromJson(Map<String, Object?> json) =>
      _$ProposalConflictOutFromJson(json);

  final String message;
  final ProposalDetailOut proposal;

  Map<String, Object?> toJson() => _$ProposalConflictOutToJson(this);
}
