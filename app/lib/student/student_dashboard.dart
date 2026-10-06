import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api.dart';
import '../api/errors.dart';
import '../dashboards/dashboard_scaffold.dart';
import 'format.dart';
import 'student_state.dart';

/// The Student's one screen: pick items and a pickup slot, see the exact
/// price, and place the order. Modify, cancel and tracking join it once their
/// endpoints exist.
class StudentDashboard extends ConsumerWidget {
  const StudentDashboard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final order = ref.watch(checkoutProvider.select((c) => c.order));
    return DashboardScaffold(
      title: 'Student',
      body: Align(
        alignment: Alignment.topCenter,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 720),
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: order != null
                ? [_OrderPlaced(order)]
                : const [
                    _Heading('Menu'),
                    _Menu(),
                    SizedBox(height: 24),
                    _Heading('Pickup slot'),
                    _Slots(),
                    SizedBox(height: 24),
                    _Heading('Your order'),
                    _CheckoutPanel(),
                  ],
          ),
        ),
      ),
    );
  }
}

class _Heading extends StatelessWidget {
  const _Heading(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Semantics(
        header: true,
        child: Text(text, style: Theme.of(context).textTheme.titleLarge),
      ),
    );
  }
}

/// Loading, failure (with a retry) or the loaded value.
class _Loaded<T> extends StatelessWidget {
  const _Loaded({
    required this.value,
    required this.onRetry,
    required this.builder,
  });

  final AsyncValue<T> value;
  final VoidCallback onRetry;
  final Widget Function(T data) builder;

  @override
  Widget build(BuildContext context) {
    return value.when(
      skipLoadingOnRefresh: true,
      data: builder,
      loading: () => const Padding(
        padding: EdgeInsets.all(24),
        child: Center(child: CircularProgressIndicator()),
      ),
      error: (error, _) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(describeApiError(error)),
          TextButton(onPressed: onRetry, child: const Text('Try again')),
        ],
      ),
    );
  }
}

class _Menu extends ConsumerWidget {
  const _Menu();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return _Loaded(
      value: ref.watch(menuProvider),
      onRetry: () => ref.invalidate(menuProvider),
      builder: (menu) {
        if (menu.items.isEmpty) {
          return const Text('No menu has been published for today yet.');
        }
        return Column(
          children: [for (final item in menu.items) _MenuItemTile(item)],
        );
      },
    );
  }
}

class _MenuItemTile extends ConsumerWidget {
  const _MenuItemTile(this.item);

  final MenuItemOut item;

  String get _availability {
    if (item.orderable) return '${item.availablePortions} left';
    return switch (item.notOrderableReason) {
      NotOrderableReason.soldOut => 'Sold out',
      _ => 'Unavailable',
    };
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final quantity = ref.watch(
      cartProvider.select((c) => c.quantityOf(item.id)),
    );
    final cart = ref.read(cartProvider.notifier);
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Text(item.name, style: theme.textTheme.titleMedium),
                ),
                Text(
                  formatPaise(item.pricePaise),
                  style: theme.textTheme.titleMedium,
                ),
              ],
            ),
            if (item.description.isNotEmpty) Text(item.description),
            Row(
              children: [
                Expanded(
                  child: Text(
                    _availability,
                    style: item.orderable
                        ? null
                        : TextStyle(color: theme.colorScheme.error),
                  ),
                ),
                IconButton(
                  key: Key('remove-${item.id}'),
                  tooltip: 'Remove one ${item.name}',
                  icon: const Icon(Icons.remove_circle_outline),
                  onPressed: quantity == 0
                      ? null
                      : () => cart.setQuantity(item.id, quantity - 1),
                ),
                Text('$quantity', key: Key('quantity-${item.id}')),
                IconButton(
                  key: Key('add-${item.id}'),
                  tooltip: 'Add one ${item.name}',
                  icon: const Icon(Icons.add_circle_outline),
                  onPressed: item.orderable && quantity < item.availablePortions
                      ? () => cart.setQuantity(item.id, quantity + 1)
                      : null,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

String _seats(int remaining) {
  return remaining == 1 ? '1 seat left' : '$remaining seats left';
}

class _Slots extends ConsumerWidget {
  const _Slots();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final selected = ref.watch(cartProvider.select((c) => c.slotId));
    return _Loaded(
      value: ref.watch(slotsProvider),
      onRetry: () => ref.invalidate(slotsProvider),
      builder: (day) {
        if (day.slots.isEmpty) {
          return const Text('No pickup slots have been set up for today yet.');
        }
        return Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final slot in day.slots)
              ChoiceChip(
                key: Key('slot-${slot.id}'),
                label: Text(
                  '${formatSlot(slot.startsAt, slot.endsAt)} · '
                  '${_slotStatus(slot)}',
                ),
                selected: slot.id == selected,
                onSelected: slot.bookable
                    ? (_) => ref.read(cartProvider.notifier).selectSlot(slot.id)
                    : null,
              ),
          ],
        );
      },
    );
  }

  String _slotStatus(SlotAvailabilityOut slot) {
    if (slot.bookable) return _seats(slot.remainingSeats);
    return switch (slot.notBookableReason) {
      NotBookableReason.full => 'Full',
      _ => 'Closed',
    };
  }
}

class _CheckoutPanel extends ConsumerWidget {
  const _CheckoutPanel();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cart = ref.watch(cartProvider);
    final checkout = ref.watch(checkoutProvider);
    final controller = ref.read(checkoutProvider.notifier);
    final quote = checkout.quote;
    final error = checkout.error;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (quote == null && !cart.isReady)
          const Text('Add at least one item and choose a pickup slot.'),
        if (quote != null) _QuoteBreakdown(quote),
        if (error != null)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Semantics(
              liveRegion: true,
              child: Text(
                error,
                key: const Key('checkout-error'),
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
          ),
        const SizedBox(height: 8),
        if (quote == null)
          FilledButton(
            key: const Key('review'),
            onPressed: cart.isReady && !checkout.busy
                ? controller.review
                : null,
            child: Text(checkout.busy ? 'Getting the price…' : 'Review order'),
          )
        else
          FilledButton(
            key: const Key('confirm'),
            onPressed: checkout.busy ? null : controller.confirm,
            child: Text(
              checkout.busy
                  ? 'Placing your order…'
                  : 'Confirm and pay ${formatPaise(quote.payablePaise)}',
            ),
          ),
      ],
    );
  }
}

/// NFR-32: the full price breakdown and the slot's remaining seats, shown
/// before the Student confirms.
class _QuoteBreakdown extends ConsumerWidget {
  const _QuoteBreakdown(this.quote, {this.showSlot = true});

  final QuoteOut quote;
  final bool showSlot;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final slot = ref
        .watch(slotsProvider)
        .value
        ?.slots
        .where((slot) => slot.id == quote.slotId)
        .firstOrNull;
    final bold = Theme.of(context).textTheme.titleMedium;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          key: const Key('quote'),
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            for (final line in quote.lines) ...[
              _AmountRow('${line.qty} × ${line.name}', line.lineBasePaise),
              if (line.lineDiscountPaise > 0)
                _AmountRow(
                  '  Discount ${line.discountPct}%',
                  -line.lineDiscountPaise,
                ),
            ],
            const Divider(),
            _AmountRow('Subtotal', quote.discountedSubtotalPaise),
            if (quote.subsidyPaise > 0)
              _AmountRow('Subsidy', -quote.subsidyPaise),
            if (quote.roundingAdjustmentPaise != 0)
              _AmountRow('Rounding', quote.roundingAdjustmentPaise),
            _AmountRow('To pay', quote.payablePaise, style: bold),
            if (showSlot && slot != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  'Pickup ${formatSlot(slot.startsAt, slot.endsAt)} · '
                  '${_seats(slot.remainingSeats)}',
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _AmountRow extends StatelessWidget {
  const _AmountRow(this.label, this.paise, {this.style});

  final String label;
  final int paise;
  final TextStyle? style;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          Expanded(child: Text(label, style: style)),
          Text(formatPaise(paise), style: style),
        ],
      ),
    );
  }
}

class _OrderPlaced extends ConsumerWidget {
  const _OrderPlaced(this.order);

  final OrderOut order;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final slot = ref
        .watch(slotsProvider)
        .value
        ?.slots
        .where((slot) => slot.id == order.slotId)
        .firstOrNull;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const _Heading('Order confirmed'),
        Text('You paid ${formatPaise(order.paidPaise)}.'),
        if (slot != null)
          Text('Pick it up between ${formatSlot(slot.startsAt, slot.endsAt)}.'),
        const SizedBox(height: 8),
        _QuoteBreakdown(order.price, showSlot: false),
        const SizedBox(height: 16),
        OutlinedButton(
          key: const Key('place-another'),
          onPressed: ref.read(checkoutProvider.notifier).placeAnother,
          child: const Text('Place another order'),
        ),
      ],
    );
  }
}
