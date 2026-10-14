import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api.dart';
import '../dashboards/common.dart';
import '../student/format.dart';
import 'admin_state.dart';

/// FR-50, FR-63: start a planning run, and read each run's report.
class AgentTab extends ConsumerStatefulWidget {
  const AgentTab({super.key});

  @override
  ConsumerState<AgentTab> createState() => _AgentTabState();
}

class _AgentTabState extends ConsumerState<AgentTab> {
  bool _busy = false;
  String? _message;

  Future<void> _trigger() async {
    setState(() => _busy = true);
    final message = await ref.read(agentRunsProvider.notifier).trigger();
    if (mounted) {
      setState(() {
        _busy = false;
        _message = message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final runs = ref.watch(agentRunsProvider);
    final active = runs.value?.any((r) => isRunActive(r.status)) ?? false;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const SectionHeading('Planning agent'),
        const Text(
          'The agent reviews demand and stock and drafts proposals. It runs '
          'on its own before service; start it here to plan again.',
        ),
        const SizedBox(height: 8),
        FilledButton.icon(
          key: const Key('trigger-run'),
          onPressed: _busy || active ? null : _trigger,
          icon: const Icon(Icons.play_arrow),
          label: Text(active ? 'A run is in progress…' : 'Run planning now'),
        ),
        if (_message case final message?)
          FormMessage(message, key: const Key('trigger-message')),
        const SizedBox(height: 24),
        const SectionHeading('Run history'),
        Loaded(
          value: runs,
          onRetry: () => ref.invalidate(agentRunsProvider),
          builder: (history) => Column(
            children: [
              if (history.isEmpty) const Text('No runs yet.'),
              for (final run in history) _RunTile(run),
            ],
          ),
        ),
      ],
    );
  }
}

class _RunTile extends StatelessWidget {
  const _RunTile(this.run);

  final AgentRunOut run;

  @override
  Widget build(BuildContext context) {
    final source = switch (run.source) {
      AgentSource.llm => ' · AI agent',
      AgentSource.heuristic => ' · heuristic fallback',
      _ => '',
    };
    return Card(
      child: ExpansionTile(
        key: Key('run-${run.id}'),
        title: Text(
          '${_statusLabel(run.status)}$source',
          key: Key('run-status-${run.id}'),
        ),
        subtitle: Text(
          '${run.trigger == AgentTrigger.scheduled ? 'Scheduled' : 'On demand'}'
          ' · started ${formatIstTime(run.startedAt)}',
        ),
        childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        expandedCrossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (isRunActive(run.status))
            const Text('The report appears when the run finishes.')
          else
            _RunReport(run.id),
        ],
      ),
    );
  }
}

String _statusLabel(AgentRunStatus status) => switch (status) {
  AgentRunStatus.queued => 'Queued',
  AgentRunStatus.running => 'Running',
  AgentRunStatus.succeeded => 'Finished',
  AgentRunStatus.failed => 'Failed',
  AgentRunStatus.$unknown => 'Unknown',
};

/// FR-52: the briefing, the per-item forecast and what the run proposed.
class _RunReport extends ConsumerWidget {
  const _RunReport(this.runId);

  final String runId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Loaded(
      value: ref.watch(agentRunProvider(runId)),
      onRetry: () => ref.invalidate(agentRunProvider(runId)),
      builder: (detail) {
        final report = detail.report is Map ? detail.report as Map : const {};
        final forecast = report['forecast'];
        final narrative = report['narrative'];
        final fallback = report['fallback_reason'];
        final error = report['error'];
        return Column(
          key: Key('report-$runId'),
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (error != null) Text('The run failed: $error'),
            if (narrative is String) Text(narrative),
            if (fallback != null)
              Text(
                'Planned by the heuristic because: $fallback',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            if (forecast is List && forecast.isNotEmpty) ...[
              const SizedBox(height: 8),
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: DataTable(
                  columns: const [
                    DataColumn(label: Text('Item')),
                    DataColumn(label: Text('Left'), numeric: true),
                    DataColumn(label: Text('Forecast'), numeric: true),
                    DataColumn(label: Text('Risk')),
                    DataColumn(label: Text('Runs out')),
                  ],
                  rows: [
                    for (final row in forecast)
                      if (row is Map) _forecastRow(row),
                  ],
                ),
              ),
            ],
            const SizedBox(height: 8),
            Text(
              '${detail.proposals.length} proposal(s) drafted · '
              '${detail.toolCalls.length} tool call(s) logged',
            ),
          ],
        );
      },
    );
  }

  DataRow _forecastRow(Map<dynamic, dynamic> row) {
    final stockout = DateTime.tryParse('${row['stockout_slot_start']}');
    return DataRow(
      cells: [
        DataCell(Text('${row['item_name']}')),
        DataCell(Text('${row['available']}')),
        DataCell(Text('${row['forecast_demand']}')),
        DataCell(Text('${row['risk']}')),
        DataCell(Text(stockout == null ? '—' : formatIstTime(stockout))),
      ],
    );
  }
}
