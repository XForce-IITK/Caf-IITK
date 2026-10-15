import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api.dart';
import '../api/errors.dart';
import '../dashboards/common.dart';
import '../student/format.dart';
import 'admin_state.dart';

/// FR-8, FR-11, FR-14: add items, set today's portions, and flag an item
/// unavailable or clear the flag.
class ItemsTab extends ConsumerWidget {
  const ItemsTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const SectionHeading("Today's items"),
        Loaded(
          value: ref.watch(adminMenuProvider),
          onRetry: () => ref.invalidate(adminMenuProvider),
          builder: (menu) => Column(
            children: [
              if (menu.items.isEmpty) const Text('No items on the menu yet.'),
              for (final item in menu.items)
                _ItemRow(item, key: Key('item-${item.id}')),
            ],
          ),
        ),
        const SizedBox(height: 24),
        const SectionHeading('Add an item'),
        const _OnboardForm(),
      ],
    );
  }
}

class _ItemRow extends ConsumerStatefulWidget {
  const _ItemRow(this.item, {super.key});

  final MenuItemOut item;

  @override
  ConsumerState<_ItemRow> createState() => _ItemRowState();
}

class _ItemRowState extends ConsumerState<_ItemRow> {
  final _total = TextEditingController();
  bool _busy = false;
  String? _message;
  bool _failed = false;

  MenuItemOut get _item => widget.item;

  bool get _flagged =>
      _item.notOrderableReason == NotOrderableReason.unavailable;

  @override
  void dispose() {
    _total.dispose();
    super.dispose();
  }

  Future<void> _run(Future<String> Function() action) async {
    setState(() => _busy = true);
    String message;
    var failed = false;
    try {
      message = await action();
    } on Object catch (error) {
      message = describeApiError(error);
      failed = true;
    }
    if (!mounted) return;
    setState(() {
      _busy = false;
      _message = message;
      _failed = failed;
    });
    if (!failed) ref.invalidate(adminMenuProvider);
  }

  Future<void> _setPortions() async {
    final total = int.tryParse(_total.text.trim());
    if (total == null || total < 0 || total > 500) {
      setState(() {
        _message = 'Enter a number of portions from 0 to 500.';
        _failed = true;
      });
      return;
    }
    await _run(() async {
      final saved = await ref
          .read(apiProvider)
          .inventory
          .setInventory(
            serviceDate: istToday(),
            itemId: _item.id,
            body: InventorySet(total: total),
          );
      _total.clear();
      return 'Portions set to ${saved.total} (${saved.available} left).';
    });
  }

  Future<void> _toggleFlag() async {
    final catalogue = ref.read(apiProvider).catalogue;
    if (_flagged) {
      await _run(() async {
        await catalogue.clearItemFlag(itemId: _item.id);
        return '${_item.name} can be ordered again.';
      });
      return;
    }
    final reason = await showDialog<String>(
      context: context,
      builder: (_) => _FlagDialog(_item.name),
    );
    if (reason == null) return;
    await _run(() async {
      await catalogue.flagItem(
        itemId: _item.id,
        body: FlagRequest(reason: reason),
      );
      return '${_item.name} is marked unavailable.';
    });
  }

  @override
  Widget build(BuildContext context) {
    final id = _item.id;
    final status = switch (_item.notOrderableReason) {
      NotOrderableReason.unavailable => 'Unavailable',
      NotOrderableReason.soldOut => 'Sold out',
      _ => 'On sale',
    };
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '${_item.name} · ${formatPaise(_item.pricePaise)}',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            Text(
              '$status · ${_item.availablePortions} portions left today',
              key: Key('item-status-$id'),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                SizedBox(
                  width: 160,
                  child: TextField(
                    key: Key('portions-$id'),
                    controller: _total,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: 'Total portions today',
                      isDense: true,
                    ),
                  ),
                ),
                OutlinedButton(
                  key: Key('set-portions-$id'),
                  onPressed: _busy ? null : _setPortions,
                  child: const Text('Set'),
                ),
                TextButton(
                  key: Key('flag-$id'),
                  onPressed: _busy ? null : _toggleFlag,
                  child: Text(_flagged ? 'Make available' : 'Mark unavailable'),
                ),
              ],
            ),
            if (_message case final message?)
              FormMessage(
                message,
                key: Key('item-message-$id'),
                isError: _failed,
              ),
          ],
        ),
      ),
    );
  }
}

class _FlagDialog extends StatefulWidget {
  const _FlagDialog(this.itemName);

  final String itemName;

  @override
  State<_FlagDialog> createState() => _FlagDialogState();
}

class _FlagDialogState extends State<_FlagDialog> {
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
      title: Text('Mark ${widget.itemName} unavailable'),
      content: TextField(
        key: const Key('flag-reason'),
        controller: _reason,
        autofocus: true,
        maxLength: 200,
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
          key: const Key('confirm-flag'),
          onPressed: _submit,
          child: const Text('Mark unavailable'),
        ),
      ],
    );
  }
}

/// FR-8 / US-06: a new ACTIVE item; price in rupees, sent as paise.
class _OnboardForm extends ConsumerStatefulWidget {
  const _OnboardForm();

  @override
  ConsumerState<_OnboardForm> createState() => _OnboardFormState();
}

class _OnboardFormState extends ConsumerState<_OnboardForm> {
  final _name = TextEditingController();
  final _description = TextEditingController();
  final _price = TextEditingController();
  ItemCategory _category = ItemCategory.meal;
  bool _busy = false;
  String? _message;
  bool _failed = false;

  @override
  void dispose() {
    _name.dispose();
    _description.dispose();
    _price.dispose();
    super.dispose();
  }

  /// "80" or "80.50" rupees as paise; null if it is not a price.
  static int? _paise(String text) {
    final match = RegExp(r'^(\d{1,3})(?:\.(\d{1,2}))?$')
        .firstMatch(text.trim());
    if (match == null) return null;
    final fraction = (match.group(2) ?? '').padRight(2, '0');
    return int.parse(match.group(1)!) * 100 + int.parse(fraction);
  }

  Future<void> _submit() async {
    final name = _name.text.trim();
    final paise = _paise(_price.text);
    if (name.isEmpty || paise == null || paise < 100 || paise > 50000) {
      setState(() {
        _message = 'Enter a name and a price from ₹1 to ₹500.';
        _failed = true;
      });
      return;
    }
    setState(() => _busy = true);
    try {
      final item = await ref
          .read(apiProvider)
          .catalogue
          .onboardItem(
            body: ItemCreate(
              name: name,
              description: _description.text.trim(),
              category: _category,
              pricePaise: paise,
            ),
          );
      _name.clear();
      _description.clear();
      _price.clear();
      ref.invalidate(adminMenuProvider);
      _message = '${item.name} added. Set its portions to put it on sale.';
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
        TextField(
          key: const Key('new-item-name'),
          controller: _name,
          maxLength: 60,
          decoration: const InputDecoration(labelText: 'Name'),
        ),
        TextField(
          key: const Key('new-item-description'),
          controller: _description,
          maxLength: 300,
          decoration: const InputDecoration(labelText: 'Description'),
        ),
        Row(
          children: [
            Expanded(
              child: TextField(
                key: const Key('new-item-price'),
                controller: _price,
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                ),
                decoration: const InputDecoration(labelText: 'Price (₹)'),
              ),
            ),
            const SizedBox(width: 16),
            DropdownButton<ItemCategory>(
              key: const Key('new-item-category'),
              value: _category,
              onChanged: (value) => setState(() => _category = value!),
              items: [
                for (final category in ItemCategory.values)
                  if (category != ItemCategory.$unknown)
                    DropdownMenuItem(
                      value: category,
                      child: Text(_categoryLabel(category)),
                    ),
              ],
            ),
          ],
        ),
        const SizedBox(height: 8),
        FilledButton(
          key: const Key('add-item'),
          onPressed: _busy ? null : _submit,
          child: const Text('Add item'),
        ),
        if (_message case final message?)
          FormMessage(
            message,
            key: const Key('add-item-message'),
            isError: _failed,
          ),
      ],
    );
  }
}

String _categoryLabel(ItemCategory category) => switch (category) {
  ItemCategory.meal => 'Meal',
  ItemCategory.snack => 'Snack',
  ItemCategory.beverage => 'Beverage',
  ItemCategory.dessert => 'Dessert',
  ItemCategory.$unknown => 'Other',
};
