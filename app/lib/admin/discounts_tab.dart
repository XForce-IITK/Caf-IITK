import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api.dart';
import '../api/errors.dart';
import '../dashboards/common.dart';
import '../student/format.dart';
import 'admin_state.dart';

/// FR-22: every discount rule, active or not, by start time.
final discountRulesProvider = FutureProvider.autoDispose<List<DiscountRuleOut>>(
  (ref) => ref.watch(apiProvider).pricing.listDiscountRules(),
  retry: (_, _) => null,
);

/// FR-22 and the SRS limits a rule's percentage to 1-50.
const minDiscountPct = 1;
const maxDiscountPct = 50;

final _clock = RegExp(r'^([01]\d|2[0-3]):[0-5]\d$');

/// "12:00:00" from the server, shown and edited as "12:00".
String _hhmm(String time) => time.length >= 5 ? time.substring(0, 5) : time;

String scopeLabel(
  DiscountRuleOut rule,
  Map<String, String> itemNames,
) => switch (rule.scope) {
  DiscountScope.all => 'All items',
  DiscountScope.category => switch (rule.category) {
    final category? => 'Category: ${categoryLabel(category)}',
    null => 'Category',
  },
  DiscountScope.items =>
    'Items: ${rule.itemIds.map((id) => itemNames[id] ?? 'removed item').join(', ')}',
  DiscountScope.$unknown => 'Unknown scope',
};

/// The whole rule as a PATCH body. The generated client sends unset fields as
/// null, which the server refuses for everything but `category`, so an edit
/// always sends every field.
DiscountRuleUpdate _fullUpdate(
  DiscountRuleOut rule, {
  String? name,
  String? startTime,
  String? endTime,
  int? pct,
  DiscountScope? scope,
  ItemCategory? category,
  List<String>? itemIds,
  bool? active,
}) {
  final newScope = scope ?? rule.scope;
  return DiscountRuleUpdate(
    name: name ?? rule.name,
    startTime: startTime ?? _hhmm(rule.startTime),
    endTime: endTime ?? _hhmm(rule.endTime),
    pct: pct ?? rule.pct,
    scope: newScope,
    category: newScope == DiscountScope.category
        ? (category ?? rule.category)
        : null,
    itemIds: newScope == DiscountScope.items ? (itemIds ?? rule.itemIds) : [],
    active: active ?? rule.active,
  );
}

/// FR-22 / US-17: create, edit, deactivate and reactivate time-of-day
/// discount rules.
class DiscountsTab extends ConsumerStatefulWidget {
  const DiscountsTab({super.key});

  @override
  ConsumerState<DiscountsTab> createState() => _DiscountsTabState();
}

class _DiscountsTabState extends ConsumerState<DiscountsTab> {
  /// The rule being edited in the form, or null when the form adds a rule.
  DiscountRuleOut? _editing;

  @override
  Widget build(BuildContext context) {
    final menu = ref.watch(adminMenuProvider).value;
    final itemNames = <String, String>{
      for (final item in menu?.items ?? const <MenuItemOut>[])
        item.id: item.name,
    };
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const SectionHeading('Discount rules'),
        const Text(
          'A rule discounts orders for slots that start inside its time range. '
          'Rules may overlap; each item gets only the highest percentage.',
        ),
        const SizedBox(height: 8),
        Loaded(
          value: ref.watch(discountRulesProvider),
          onRetry: () => ref.invalidate(discountRulesProvider),
          builder: (rules) => Column(
            children: [
              if (rules.isEmpty) const Text('No discount rules yet.'),
              for (final rule in rules)
                _RuleRow(
                  rule,
                  itemNames: itemNames,
                  onEdit: () => setState(() => _editing = rule),
                  key: Key('rule-${rule.id}'),
                ),
            ],
          ),
        ),
        const SizedBox(height: 24),
        SectionHeading(
          _editing == null ? 'Add a discount rule' : 'Edit ${_editing!.name}',
        ),
        _RuleForm(
          editing: _editing,
          onDone: () => setState(() => _editing = null),
          // A new form for each rule, so its fields start from that rule.
          key: ValueKey(_editing?.id ?? 'new'),
        ),
      ],
    );
  }
}

class _RuleRow extends ConsumerStatefulWidget {
  const _RuleRow(
    this.rule, {
    required this.itemNames,
    required this.onEdit,
    super.key,
  });

  final DiscountRuleOut rule;
  final Map<String, String> itemNames;
  final VoidCallback onEdit;

  @override
  ConsumerState<_RuleRow> createState() => _RuleRowState();
}

class _RuleRowState extends ConsumerState<_RuleRow> {
  bool _busy = false;
  String? _message;

  DiscountRuleOut get _rule => widget.rule;

  Future<void> _toggle() async {
    setState(() => _busy = true);
    String? message;
    try {
      await ref
          .read(apiProvider)
          .pricing
          .updateDiscountRule(
            ruleId: _rule.id,
            body: _fullUpdate(_rule, active: !_rule.active),
          );
      ref.invalidate(discountRulesProvider);
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
    final theme = Theme.of(context);
    final active = _rule.active;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '${_rule.name} · ${_rule.pct}% off',
                        style: theme.textTheme.titleMedium,
                      ),
                      Text(
                        '${_hhmm(_rule.startTime)}–${_hhmm(_rule.endTime)} · '
                        '${scopeLabel(_rule, widget.itemNames)}'
                        '${active ? '' : ' · Inactive'}',
                        key: Key('rule-summary-${_rule.id}'),
                        style: active
                            ? null
                            : TextStyle(color: theme.colorScheme.error),
                      ),
                    ],
                  ),
                ),
                TextButton(
                  key: Key('edit-rule-${_rule.id}'),
                  onPressed: _busy ? null : widget.onEdit,
                  child: const Text('Edit'),
                ),
                OutlinedButton(
                  key: Key('toggle-rule-${_rule.id}'),
                  onPressed: _busy ? null : _toggle,
                  child: Text(active ? 'Deactivate' : 'Reactivate'),
                ),
              ],
            ),
            if (_message case final message?)
              FormMessage(
                message,
                key: Key('rule-message-${_rule.id}'),
                isError: true,
              ),
          ],
        ),
      ),
    );
  }
}

class _RuleForm extends ConsumerStatefulWidget {
  const _RuleForm({required this.editing, required this.onDone, super.key});

  final DiscountRuleOut? editing;
  final VoidCallback onDone;

  @override
  ConsumerState<_RuleForm> createState() => _RuleFormState();
}

class _RuleFormState extends ConsumerState<_RuleForm> {
  late final _name = TextEditingController(text: widget.editing?.name);
  late final _start = TextEditingController(
    text: widget.editing == null ? '' : _hhmm(widget.editing!.startTime),
  );
  late final _end = TextEditingController(
    text: widget.editing == null ? '' : _hhmm(widget.editing!.endTime),
  );
  late final _pct = TextEditingController(text: widget.editing?.pct.toString());
  late DiscountScope _scope = widget.editing?.scope ?? DiscountScope.all;
  late ItemCategory? _category = widget.editing?.category;
  late final Set<String> _items = {...?widget.editing?.itemIds};
  bool _busy = false;
  String? _message;
  bool _failed = false;

  @override
  void dispose() {
    _name.dispose();
    _start.dispose();
    _end.dispose();
    _pct.dispose();
    super.dispose();
  }

  /// What is wrong with the form, or null when it can be sent.
  String? _problem() {
    final pct = int.tryParse(_pct.text.trim());
    if (_name.text.trim().isEmpty) return 'Enter a name for the rule.';
    if (!_clock.hasMatch(_start.text.trim()) ||
        !_clock.hasMatch(_end.text.trim())) {
      return 'Enter the start and end as HH:MM, for example 14:00.';
    }
    if (_start.text.trim().compareTo(_end.text.trim()) >= 0) {
      return 'The end must be after the start.';
    }
    if (pct == null || pct < minDiscountPct || pct > maxDiscountPct) {
      return 'The discount must be a whole number from $minDiscountPct to '
          '$maxDiscountPct %.';
    }
    if (_scope == DiscountScope.category && _category == null) {
      return 'Choose the category the rule applies to.';
    }
    if (_scope == DiscountScope.items && _items.isEmpty) {
      return 'Choose at least one item.';
    }
    return null;
  }

  Future<void> _submit() async {
    if (_problem() case final problem?) {
      setState(() {
        _message = problem;
        _failed = true;
      });
      return;
    }
    final name = _name.text.trim();
    final start = _start.text.trim();
    final end = _end.text.trim();
    final pct = int.parse(_pct.text.trim());
    final category = _scope == DiscountScope.category ? _category : null;
    final items = _scope == DiscountScope.items ? _items.toList() : <String>[];
    setState(() => _busy = true);
    final pricing = ref.read(apiProvider).pricing;
    final editing = widget.editing;
    try {
      final saved = editing == null
          ? await pricing.createDiscountRule(
              body: DiscountRuleCreate(
                name: name,
                startTime: start,
                endTime: end,
                pct: pct,
                scope: _scope,
                category: category,
                itemIds: items,
              ),
            )
          : await pricing.updateDiscountRule(
              ruleId: editing.id,
              body: _fullUpdate(
                editing,
                name: name,
                startTime: start,
                endTime: end,
                pct: pct,
                scope: _scope,
                category: category,
                itemIds: items,
              ),
            );
      ref.invalidate(discountRulesProvider);
      if (editing != null) {
        // Close the form: it holds the rule as it was before this save.
        if (mounted) {
          ScaffoldMessenger.of(
            context,
          ).showSnackBar(SnackBar(content: Text('${saved.name} is updated.')));
        }
        widget.onDone();
        return;
      }
      _message =
          '${saved.name} is active: ${saved.pct}% off from '
          '${_hhmm(saved.startTime)} to ${_hhmm(saved.endTime)}.';
      _failed = false;
      _name.clear();
      _start.clear();
      _end.clear();
      _pct.clear();
      _items.clear();
      _category = null;
      _scope = DiscountScope.all;
    } on Object catch (error) {
      _message = describeApiError(error);
      _failed = true;
    }
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final menu = ref.watch(adminMenuProvider);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TextField(
          key: const Key('rule-name'),
          controller: _name,
          maxLength: 60,
          decoration: const InputDecoration(labelText: 'Name'),
        ),
        Row(
          children: [
            Expanded(
              child: TextField(
                key: const Key('rule-start'),
                controller: _start,
                decoration: const InputDecoration(
                  labelText: 'From (HH:MM)',
                  helperText: 'Slots starting at this time are discounted',
                ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: TextField(
                key: const Key('rule-end'),
                controller: _end,
                decoration: const InputDecoration(
                  labelText: 'Until (HH:MM)',
                  helperText: 'Slots starting at this time are not',
                ),
              ),
            ),
          ],
        ),
        TextField(
          key: const Key('rule-pct'),
          controller: _pct,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(
            labelText: 'Discount %',
            helperText: '$minDiscountPct to $maxDiscountPct',
          ),
        ),
        const SizedBox(height: 12),
        SegmentedButton<DiscountScope>(
          key: const Key('rule-scope'),
          segments: const [
            ButtonSegment(value: DiscountScope.all, label: Text('All items')),
            ButtonSegment(
              value: DiscountScope.category,
              label: Text('A category'),
            ),
            ButtonSegment(
              value: DiscountScope.items,
              label: Text('Chosen items'),
            ),
          ],
          selected: {_scope},
          onSelectionChanged: (scopes) =>
              setState(() => _scope = scopes.single),
        ),
        if (_scope == DiscountScope.category) ...[
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            children: [
              for (final category in ItemCategory.$valuesDefined)
                ChoiceChip(
                  key: Key('rule-category-${category.json}'),
                  label: Text(categoryLabel(category)),
                  selected: _category == category,
                  onSelected: (_) => setState(() => _category = category),
                ),
            ],
          ),
        ],
        if (_scope == DiscountScope.items) ...[
          const SizedBox(height: 8),
          Loaded(
            value: menu,
            onRetry: () => ref.invalidate(adminMenuProvider),
            builder: (menu) => Wrap(
              spacing: 8,
              children: [
                if (menu.items.isEmpty) const Text('No items on the menu.'),
                for (final item in menu.items)
                  FilterChip(
                    key: Key('rule-item-${item.id}'),
                    label: Text(item.name),
                    selected: _items.contains(item.id),
                    onSelected: (selected) => setState(
                      () => selected
                          ? _items.add(item.id)
                          : _items.remove(item.id),
                    ),
                  ),
              ],
            ),
          ),
        ],
        const SizedBox(height: 12),
        Row(
          children: [
            FilledButton(
              key: const Key('save-rule'),
              onPressed: _busy ? null : _submit,
              child: Text(widget.editing == null ? 'Add rule' : 'Save changes'),
            ),
            if (widget.editing != null) ...[
              const SizedBox(width: 8),
              TextButton(
                key: const Key('cancel-edit-rule'),
                onPressed: _busy ? null : widget.onDone,
                child: const Text('Cancel'),
              ),
            ],
          ],
        ),
        if (_message case final message?)
          FormMessage(
            message,
            key: const Key('rule-message'),
            isError: _failed,
          ),
      ],
    );
  }
}
