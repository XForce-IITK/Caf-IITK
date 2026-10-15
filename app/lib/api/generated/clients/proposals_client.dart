// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:dio/dio.dart';
import 'package:retrofit/retrofit.dart';

import '../models/proposal_detail_out.dart';
import '../models/proposal_status.dart';
import '../models/reject_request.dart';

part 'proposals_client.g.dart';

@RestApi()
abstract class ProposalsClient {
  factory ProposalsClient(Dio dio, {String? baseUrl}) = _ProposalsClient;

  /// List Proposals.
  ///
  /// UC-25 step 1: proposals, newest first; PENDING only unless another status is asked for.
  ///
  /// Proposals whose target start has passed, or that a newer one superseded, are.
  /// expired first (FR-56). Each names its run, whose report holds the forecast.
  @GET('/api/v1/admin/proposals')
  Future<List<ProposalDetailOut>> listProposals({
    @Query('status') ProposalStatus? status = ProposalStatus.pending,
  });

  /// Approve Proposal.
  ///
  /// FR-56, FR-57: re-validate, then apply the change, all in one transaction.
  ///
  /// Item-disable flags the item until the end of the target date (FR-53), prep.
  /// priority orders the slot's kitchen totals (FR-54) and replenishment adds the.
  /// portions (FR-55), under the Administrator's identity with an audit entry that.
  /// links the proposal.
  @POST('/api/v1/admin/proposals/{proposal_id}/approve')
  Future<ProposalDetailOut> approveProposal({
    @Path('proposal_id') required String proposalId,
  });

  /// Reject Proposal.
  ///
  /// FR-56: REJECTED with the Administrator's reason; nothing is applied.
  @POST('/api/v1/admin/proposals/{proposal_id}/reject')
  Future<ProposalDetailOut> rejectProposal({
    @Path('proposal_id') required String proposalId,
    @Body() required RejectRequest body,
  });
}
