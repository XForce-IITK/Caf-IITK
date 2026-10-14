import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api.dart';
import '../dashboards/common.dart';
import '../student/format.dart';
import 'admin_state.dart';

/// UC-25: every PENDING proposal with what it would change, why, and Approve
/// or Reject. Nothing changes without one of these decisions.
class ProposalsTab extends ConsumerWidget {
  const ProposalsTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Loaded(
      value: ref.watch(pendingProposalsProvider),
      onRetry: () => ref.invalidate(pendingProposalsProvider),
      builder: (proposals) => RefreshIndicator(
        onRefresh: () => ref.refresh(pendingProposalsProvider.future),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Row(
              children: [
                const Expanded(child: SectionHeading('Waiting for a decision')),
                IconButton(
                  key: const Key('refresh-proposals'),
                  tooltip: 'Refresh',
                  icon: const Icon(Icons.refresh),
                  onPressed: () => ref.invalidate(pendingProposalsProvider),
                ),
              ],
            ),
            if (ref.watch(lastDecisionProvider) case final decision?)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: FormMessage(
                  decision.message,
                  key: const Key('last-decision'),
                  isError: decision.failed,
                ),
              ),
            if (proposals.isEmpty)
              const Text(
                'No proposals are waiting. Run the planning agent from the '
                'Agent runs tab.',
                key: Key('no-proposals'),
              ),
            for (final proposal in proposals)
              ProposalCard(proposal, key: Key('proposal-${proposal.id}')),
          ],
        ),
      ),
    );
  }
}

class ProposalCard extends ConsumerStatefulWidget {
  const ProposalCard(this.proposal, {super.key});

  final ProposalDetailOut proposal;

  @override
  ConsumerState<ProposalCard> createState() => _ProposalCardState();
}

class _ProposalCardState extends ConsumerState<ProposalCard> {
  bool _busy = false;

  ProposalDetailOut get _proposal => widget.proposal;

  Future<void> _decide({String? rejectReason}) async {
    setState(() => _busy = true);
    await decideProposal(ref, _proposal, rejectReason: rejectReason);
    if (mounted) setState(() => _busy = false);
  }

  Future<void> _reject() async {
    final reason = await showDialog<String>(
      context: context,
      builder: (_) => const _RejectDialog(),
    );
    if (reason != null) await _decide(rejectReason: reason);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final menu = ref.watch(adminMenuProvider).value;
    final names = {
      for (final item in menu?.items ?? <MenuItemOut>[]) item.id: item.name,
    };
    String name(Object? id) => names[id] ?? 'item …${_tail('$id')}';
    final id = _proposal.id;
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(_title(_proposal.type), style: theme.textTheme.titleMedium),
            const SizedBox(height: 4),
            Text(_content(name), key: Key('proposal-content-$id')),
            const SizedBox(height: 4),
            Text('Why: ${_proposal.rationale}'),
            Text(
              'Drafted by ${_proposal.source == AgentSource.heuristic ? 'the heuristic planner' : 'the AI agent'}'
              ' · expires ${formatIstTime(_proposal.expiresAt)}',
              style: theme.textTheme.bodySmall,
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: [
                FilledButton(
                  key: Key('approve-$id'),
                  onPressed: _busy ? null : _decide,
                  child: const Text('Approve'),
                ),
                OutlinedButton(
                  key: Key('reject-$id'),
                  onPressed: _busy ? null : _reject,
                  child: const Text('Reject'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  String _content(String Function(Object?) name) {
    final payload = _proposal.payload;
    final data = payload is Map ? payload : const {};
    switch (_proposal.type) {
      case ProposalType.disable:
        return 'Mark ${name(data['item_id'])} unavailable for the rest of '
            '${_date(_proposal.targetDate)}. Reason: ${data['reason']}';
      case ProposalType.replenish:
        final lines = data['lines'];
        final added = [
          if (lines is List)
            for (final line in lines)
              if (line is Map)
                '${name(line['item_id'])} +${line['additional_portions']}',
        ];
        return 'Add portions for ${_date(_proposal.targetDate)}: '
            '${added.join(', ')}';
      case ProposalType.prepPriority:
        final ids = data['item_ids'];
        final order = [
          if (ids is List)
            for (final (index, itemId) in ids.indexed)
              '${index + 1}. ${name(itemId)}',
        ];
        return 'Prepare in this order for the ${_slotLabel()} slot: '
            '${order.join('  ')}';
      case ProposalType.$unknown:
        return 'Unknown proposal type.';
    }
  }

  String _slotLabel() {
    final slotId = _proposal.targetSlotId;
    final slots = ref.watch(adminSlotsProvider(_proposal.targetDate)).value;
    final slot = slots?.slots.where((s) => s.id == slotId).firstOrNull;
    return slot == null ? 'target' : formatSlot(slot.startsAt, slot.endsAt);
  }
}

String _title(ProposalType type) => switch (type) {
  ProposalType.disable => 'Disable an item',
  ProposalType.replenish => 'Replenish stock',
  ProposalType.prepPriority => 'Prep priority',
  ProposalType.$unknown => 'Proposal',
};

String _date(DateTime date) =>
    '${date.day.toString().padLeft(2, '0')}/${date.month.toString().padLeft(2, '0')}';

String _tail(String id) => id.length <= 6 ? id : id.substring(id.length - 6);

/// UC-25 2a: a rejection needs a reason; the dialog will not return without one.
class _RejectDialog extends StatefulWidget {
  const _RejectDialog();

  @override
  State<_RejectDialog> createState() => _RejectDialogState();
}

class _RejectDialogState extends State<_RejectDialog> {
  final _reason = TextEditingController();
  bool _missing = false;

  @override
  void dispose() {
    _reason.dispose();
    super.dispose();
  }

  void _submit() {
    final reason = _reason.text.trim();
    if (reason.isEmpty) {
      setState(() => _missing = true);
      return;
    }
    Navigator.of(context).pop(reason);
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Reject proposal'),
      content: TextField(
        key: const Key('reject-reason'),
        controller: _reason,
        autofocus: true,
        maxLength: 300,
        decoration: InputDecoration(
          labelText: 'Reason',
          errorText: _missing ? 'A reason is required' : null,
        ),
        onSubmitted: (_) => _submit(),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: const Key('confirm-reject'),
          onPressed: _submit,
          child: const Text('Reject'),
        ),
      ],
    );
  }
}
