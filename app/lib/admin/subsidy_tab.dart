import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api.dart';
import '../api/errors.dart';
import '../dashboards/common.dart';
import '../student/format.dart';

/// FR-23: P-SUBSIDY_AMT (paise) and P-SUBSIDY_CAP_PCT.
final subsidySettingsProvider = FutureProvider.autoDispose<SubsidySettings>(
  (ref) => ref.watch(apiProvider).pricing.getSubsidySettings(),
  retry: (_, _) => null,
);

/// Students matching a search, optionally only the eligible ones.
final subsidyStudentsProvider = FutureProvider.autoDispose
    .family<List<StudentOut>, ({String search, bool eligibleOnly})>(
      (ref, query) => ref
          .watch(apiProvider)
          .pricing
          .listStudents(
            search: query.search.isEmpty ? null : query.search,
            eligible: query.eligibleOnly ? true : null,
          ),
      retry: (_, _) => null,
    );

/// The server's limit on P-SUBSIDY_AMT: the dearest item allowed, ₹500.
const maxSubsidyPaise = 50000;

final _rupees = RegExp(r'^\d+(\.\d{1,2})?$');

/// "12.5" -> 1250 paise; null when it is not an amount in rupees.
int? parseRupees(String text) {
  final value = text.trim();
  if (!_rupees.hasMatch(value)) return null;
  final [whole, ...fraction] = value.split('.');
  final paise = fraction.isEmpty
      ? 0
      : int.parse(fraction.single.padRight(2, '0'));
  return int.parse(whole) * 100 + paise;
}

String _rupeeText(int paise) =>
    paise % 100 == 0 ? '${paise ~/ 100}' : (paise / 100).toStringAsFixed(2);

/// FR-23 / US-18: the subsidy settings, and which Students are eligible.
class SubsidyTab extends ConsumerWidget {
  const SubsidyTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const SectionHeading('Subsidy'),
        const Text(
          "An eligible Student's first order of the day gets the subsidy off, "
          'up to the cap as a share of its discounted price.',
        ),
        const SizedBox(height: 8),
        Loaded(
          value: ref.watch(subsidySettingsProvider),
          onRetry: () => ref.invalidate(subsidySettingsProvider),
          builder: (settings) => _SettingsForm(
            settings,
            key: ValueKey((settings.amountPaise, settings.capPct)),
          ),
        ),
        const SizedBox(height: 24),
        const SectionHeading('Eligible Students'),
        const _Students(),
      ],
    );
  }
}

class _SettingsForm extends ConsumerStatefulWidget {
  const _SettingsForm(this.settings, {super.key});

  final SubsidySettings settings;

  @override
  ConsumerState<_SettingsForm> createState() => _SettingsFormState();
}

class _SettingsFormState extends ConsumerState<_SettingsForm> {
  late final _amount = TextEditingController(
    text: _rupeeText(widget.settings.amountPaise),
  );
  late final _cap = TextEditingController(
    text: widget.settings.capPct.toString(),
  );
  bool _busy = false;
  String? _message;
  bool _failed = false;

  @override
  void dispose() {
    _amount.dispose();
    _cap.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final amount = parseRupees(_amount.text);
    final cap = int.tryParse(_cap.text.trim());
    if (amount == null || amount > maxSubsidyPaise) {
      setState(() {
        _message =
            'Enter an amount from ₹0 to ${formatPaise(maxSubsidyPaise)}.';
        _failed = true;
      });
      return;
    }
    if (cap == null || cap < 0 || cap > 100) {
      setState(() {
        _message = 'Enter a cap from 0 to 100 %.';
        _failed = true;
      });
      return;
    }
    setState(() => _busy = true);
    try {
      final saved = await ref
          .read(apiProvider)
          .pricing
          .setSubsidySettings(
            body: SubsidySettings(amountPaise: amount, capPct: cap),
          );
      _message = saved.amountPaise == 0
          ? 'The subsidy is off.'
          : 'Saved: ${formatPaise(saved.amountPaise)} off, at most '
                '${saved.capPct}% of the order.';
      _failed = false;
    } on Object catch (error) {
      _message = describeApiError(error);
      _failed = true;
    }
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: TextField(
                key: const Key('subsidy-amount'),
                controller: _amount,
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                ),
                decoration: const InputDecoration(
                  labelText: 'Amount (₹)',
                  helperText: '0 turns the subsidy off',
                ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: TextField(
                key: const Key('subsidy-cap'),
                controller: _cap,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: 'Cap (% of the order)',
                  helperText: '0 to 100',
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        FilledButton(
          key: const Key('save-subsidy'),
          onPressed: _busy ? null : _save,
          child: const Text('Save subsidy'),
        ),
        if (_message case final message?)
          FormMessage(
            message,
            key: const Key('subsidy-message'),
            isError: _failed,
          ),
      ],
    );
  }
}

class _Students extends ConsumerStatefulWidget {
  const _Students();

  @override
  ConsumerState<_Students> createState() => _StudentsState();
}

class _StudentsState extends ConsumerState<_Students> {
  final _search = TextEditingController();
  String _query = '';
  bool _eligibleOnly = false;

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  ({String search, bool eligibleOnly}) get _key =>
      (search: _query, eligibleOnly: _eligibleOnly);

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Expanded(
              child: TextField(
                key: const Key('student-search'),
                controller: _search,
                maxLength: 100,
                decoration: const InputDecoration(
                  labelText: 'Find a Student by name or email',
                ),
                onSubmitted: (text) => setState(() => _query = text.trim()),
              ),
            ),
            IconButton(
              key: const Key('student-search-go'),
              tooltip: 'Search',
              icon: const Icon(Icons.search),
              onPressed: () => setState(() => _query = _search.text.trim()),
            ),
          ],
        ),
        SwitchListTile(
          key: const Key('eligible-only'),
          title: const Text('Show only eligible Students'),
          value: _eligibleOnly,
          onChanged: (value) => setState(() => _eligibleOnly = value),
        ),
        Loaded(
          value: ref.watch(subsidyStudentsProvider(_key)),
          onRetry: () => ref.invalidate(subsidyStudentsProvider(_key)),
          builder: (students) => Column(
            children: [
              if (students.isEmpty) const Text('No Students match.'),
              for (final student in students)
                _StudentRow(student, key: Key('student-${student.id}')),
            ],
          ),
        ),
      ],
    );
  }
}

class _StudentRow extends ConsumerStatefulWidget {
  const _StudentRow(this.student, {super.key});

  final StudentOut student;

  @override
  ConsumerState<_StudentRow> createState() => _StudentRowState();
}

class _StudentRowState extends ConsumerState<_StudentRow> {
  late bool _eligible = widget.student.subsidyEligible;
  bool _busy = false;
  String? _message;

  Future<void> _set(bool eligible) async {
    setState(() {
      _busy = true;
      _message = null;
    });
    String? message;
    try {
      final saved = await ref
          .read(apiProvider)
          .pricing
          .setSubsidyEligibility(
            userId: widget.student.id,
            body: EligibilityUpdate(eligible: eligible),
          );
      _eligible = saved.subsidyEligible;
      // Lists filtered by eligibility are now out of date.
      ref.invalidate(subsidyStudentsProvider);
    } on Object catch (error) {
      message = describeApiError(error);
    }
    if (mounted) {
      setState(() {
        _busy = false;
        _message = message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final student = widget.student;
    return Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SwitchListTile(
            key: Key('eligible-${student.id}'),
            title: Text(student.name),
            subtitle: Text(
              '${student.email}${student.isActive ? '' : ' · Deactivated'}',
            ),
            value: _eligible,
            onChanged: _busy ? null : _set,
          ),
          if (_message case final message?)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
              child: FormMessage(
                message,
                key: Key('student-message-${student.id}'),
                isError: true,
              ),
            ),
        ],
      ),
    );
  }
}
