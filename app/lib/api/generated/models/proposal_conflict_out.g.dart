// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'proposal_conflict_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

ProposalConflictOut _$ProposalConflictOutFromJson(Map<String, dynamic> json) =>
    ProposalConflictOut(
      message: json['message'] as String,
      proposal: ProposalDetailOut.fromJson(
        json['proposal'] as Map<String, dynamic>,
      ),
    );

Map<String, dynamic> _$ProposalConflictOutToJson(
  ProposalConflictOut instance,
) => <String, dynamic>{
  'message': instance.message,
  'proposal': instance.proposal,
};
