import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api.dart';
import '../api/errors.dart';
import '../student/order_tracking.dart' show pollIntervalProvider;

/// Today's ACTIVE items with their portions left (FR-13); names proposals'
/// item IDs and backs the items and inventory tab.
final adminMenuProvider = FutureProvider.autoDispose<MenuOut>(
  (ref) => ref.watch(apiProvider).catalogue.browseMenu(),
  retry: (_, _) => null,
);

/// Pickup slots of a service date, to name a prep-priority proposal's slot.
final adminSlotsProvider = FutureProvider.autoDispose
    .family<SlotListOut, DateTime>(
      (ref, date) =>
          ref.watch(apiProvider).slots.browseSlots(date: serviceDate(date)),
      retry: (_, _) => null,
    );

/// UC-25: the proposals still waiting for a decision, newest first.
final pendingProposalsProvider =
    FutureProvider.autoDispose<List<ProposalDetailOut>>(
      (ref) => ref.watch(apiProvider).proposals.listProposals(),
      retry: (_, _) => null,
    );

/// One run with its report, proposals and tool-call log (FR-63).
final agentRunProvider = FutureProvider.autoDispose
    .family<AgentRunDetailOut, String>(
      (ref, runId) => ref.watch(apiProvider).agent.getAgentRun(runId: runId),
      retry: (_, _) => null,
    );

bool isRunActive(AgentRunStatus status) =>
    status == AgentRunStatus.queued || status == AgentRunStatus.running;

/// FR-63: run history, newest first. While a run is queued or running it is
/// refreshed every P-POLL, and the proposals list is refreshed when it ends.
final agentRunsProvider =
    AsyncNotifierProvider.autoDispose<AgentRuns, List<AgentRunOut>>(
      AgentRuns.new,
      retry: (_, _) => null,
    );

class AgentRuns extends AsyncNotifier<List<AgentRunOut>> {
  Timer? _timer;

  @override
  Future<List<AgentRunOut>> build() async {
    // Poll only while the history is on screen.
    ref.onCancel(() => _timer?.cancel());
    ref.onResume(() => _scheduleIfActive(state.value ?? const []));
    ref.onDispose(() => _timer?.cancel());
    final runs = await _fetch();
    _scheduleIfActive(runs);
    return runs;
  }

  Future<List<AgentRunOut>> _fetch() =>
      ref.read(apiProvider).agent.listAgentRuns();

  void _scheduleIfActive(List<AgentRunOut> runs) {
    _timer?.cancel();
    if (runs.any((run) => isRunActive(run.status))) {
      _timer = Timer(ref.read(pollIntervalProvider), _poll);
    }
  }

  Future<void> _poll() async {
    final before = state.value ?? const [];
    try {
      final runs = await _fetch();
      state = AsyncData(runs);
      final finished = before.any(
        (old) =>
            isRunActive(old.status) &&
            runs.any((run) => run.id == old.id && !isRunActive(run.status)),
      );
      if (finished) ref.invalidate(pendingProposalsProvider);
      _scheduleIfActive(runs);
    } on Object {
      // Keep the last history on screen and try again next time.
      _scheduleIfActive(before);
    }
  }

  /// FR-50: queue an on-demand run. Returns a message for the Administrator.
  Future<String> trigger() async {
    try {
      final run = await ref.read(apiProvider).agent.triggerAgentRun();
      final runs = [run, ...?state.value?.where((r) => r.id != run.id)];
      state = AsyncData(runs);
      _scheduleIfActive(runs);
      return 'Planning run started. Its proposals appear when it finishes.';
    } on DioException catch (error) {
      if (error.response?.statusCode == 409) {
        ref.invalidateSelf();
        return 'A planning run is already in progress.';
      }
      return describeApiError(error);
    }
  }
}

/// The outcome of deciding a proposal, to show beside it.
class Decision {
  const Decision(this.message, {this.failed = false});

  final String message;
  final bool failed;
}

/// The outcome of the last decision, shown above the list: a decided proposal
/// leaves the pending list, so its own card is gone.
final lastDecisionProvider =
    NotifierProvider.autoDispose<LastDecision, Decision?>(LastDecision.new);

class LastDecision extends Notifier<Decision?> {
  @override
  Decision? build() => null;

  void show(Decision decision) => state = decision;
}

/// FR-56, FR-57: approve or reject a proposal, then refresh what it changed.
Future<Decision> decideProposal(
  WidgetRef ref,
  ProposalDetailOut proposal, {
  String? rejectReason,
}) async {
  final api = ref.read(apiProvider).proposals;
  late Decision decision;
  try {
    if (rejectReason == null) {
      await api.approveProposal(proposalId: proposal.id);
    } else {
      await api.rejectProposal(
        proposalId: proposal.id,
        body: RejectRequest(reason: rejectReason),
      );
    }
    decision = Decision(
      rejectReason == null
          ? 'Approved and applied: ${describeProposalType(proposal.type)}.'
          : 'Rejected: ${describeProposalType(proposal.type)}.',
    );
  } on Object catch (error) {
    decision = Decision(
      (error is DioException ? _conflictMessage(error) : null) ??
          describeApiError(error),
      failed: true,
    );
  }
  ref.read(lastDecisionProvider.notifier).show(decision);
  ref.invalidate(pendingProposalsProvider);
  ref.invalidate(adminMenuProvider);
  return decision;
}

String describeProposalType(ProposalType type) => switch (type) {
  ProposalType.disable => 'disable an item',
  ProposalType.replenish => 'replenish stock',
  ProposalType.prepPriority => 'prep priority',
  ProposalType.$unknown => 'proposal',
};

/// A 409 names what happened to the proposal: decided, EXPIRED or INVALIDATED.
String? _conflictMessage(DioException error) {
  final data = error.response?.data;
  final detail = data is Map ? data['detail'] : null;
  if (error.response?.statusCode != 409 || detail is! Map) return null;
  final proposal = detail['proposal'];
  final status = proposal is Map ? proposal['status'] : null;
  final reason = proposal is Map ? proposal['decision_reason'] : null;
  return switch (status) {
    'EXPIRED' => 'Not applied: the proposal expired before it was approved.',
    'INVALIDATED' =>
      'Not applied: it no longer fits the current state. $reason',
    _ => 'Not applied: the proposal was already decided ($status).',
  };
}
