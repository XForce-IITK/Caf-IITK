import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api.dart';
import '../api/errors.dart';
import 'format.dart';
import 'order_tracking.dart';
import 'student_state.dart';

const _unchanged = 'Your order is unchanged.';

/// The Student's draft change to one order (UC-12), from editing to result.
class ModifyState {
  const ModifyState({
    this.editing = false,
    this.quantities = const {},
    this.slotId,
    this.heldQuantities = const {},
    this.heldSlotId,
    this.quote,
    this.key,
    this.busy = false,
    this.error,
    this.result,
  });

  final bool editing;
  final Map<String, int> quantities;
  final String? slotId;

  /// What the order holds now. Its own portions and seat stay available to it,
  /// so the menu's counts are raised by these (FR-35).
  final Map<String, int> heldQuantities;
  final String? heldSlotId;

  /// The price of the draft and its difference from what was paid.
  final ModificationQuoteOut? quote;

  /// One key per confirmation of [quote], reused if it is repeated (NFR-18).
  final String? key;
  final bool busy;
  final String? error;
  final ModifiedOrderOut? result;

  bool get changed {
    if (slotId != heldSlotId) return true;
    if (quantities.length != heldQuantities.length) return true;
    return quantities.entries.any((e) => heldQuantities[e.key] != e.value);
  }

  List<QuoteLineIn> get lines => [
    for (final entry in quantities.entries)
      QuoteLineIn(itemId: entry.key, qty: entry.value),
  ];

  ModifyState copyWith({
    bool? editing,
    Map<String, int>? quantities,
    String? slotId,
    ModificationQuoteOut? quote,
    bool clearQuote = false,
    String? key,
    bool clearKey = false,
    bool? busy,
    String? error,
    bool clearError = false,
    ModifiedOrderOut? result,
  }) {
    return ModifyState(
      editing: editing ?? this.editing,
      quantities: quantities ?? this.quantities,
      slotId: slotId ?? this.slotId,
      heldQuantities: heldQuantities,
      heldSlotId: heldSlotId,
      quote: clearQuote ? null : quote ?? this.quote,
      key: clearKey ? null : key ?? this.key,
      busy: busy ?? this.busy,
      error: clearError ? null : error ?? this.error,
      result: result ?? this.result,
    );
  }
}

final modifyOrderProvider = NotifierProvider.autoDispose
    .family<ModifyController, ModifyState, String>(ModifyController.new);

class ModifyController extends Notifier<ModifyState> {
  ModifyController(this.orderId);

  final String orderId;

  @override
  ModifyState build() => const ModifyState();

  OrderingClient get _ordering => ref.read(apiProvider).ordering;

  /// Start from what the order holds now.
  void start(OrderDetailOut order) {
    final held = {for (final line in order.price.lines) line.itemId: line.qty};
    state = ModifyState(
      editing: true,
      quantities: held,
      slotId: order.slotId,
      heldQuantities: held,
      heldSlotId: order.slotId,
    );
  }

  void discard() => state = const ModifyState();

  void setQuantity(String itemId, int quantity) {
    final quantities = Map.of(state.quantities);
    if (quantity <= 0) {
      quantities.remove(itemId);
    } else {
      quantities[itemId] = quantity;
    }
    // A price is only valid for the draft it was made for.
    state = state.copyWith(
      quantities: quantities,
      clearQuote: true,
      clearKey: true,
      clearError: true,
    );
  }

  void selectSlot(String slotId) {
    state = state.copyWith(
      slotId: slotId,
      clearQuote: true,
      clearKey: true,
      clearError: true,
    );
  }

  /// UC-12 step 3: price the draft. Reserves nothing.
  Future<void> review() async {
    if (state.busy || state.quantities.isEmpty || !state.changed) return;
    state = state.copyWith(busy: true, clearError: true);
    try {
      final quote = await _ordering.quoteOrderModification(
        orderId: orderId,
        body: QuoteRequest(slotId: state.slotId!, lines: state.lines),
      );
      state = state.copyWith(
        busy: false,
        quote: quote,
        key: newIdempotencyKey(),
      );
    } on Object catch (error) {
      state = state.copyWith(busy: false, error: describeApiError(error));
    }
  }

  /// FR-35, FR-36: apply the draft at the price shown, at [version].
  Future<void> confirm(int version) async {
    final quote = state.quote;
    final key = state.key;
    if (state.busy || quote == null || key == null) return;
    state = state.copyWith(busy: true, clearError: true);
    try {
      final result = await _ordering.modifyOrder(
        orderId: orderId,
        idempotencyKey: key,
        body: ModifyOrderRequest(
          slotId: state.slotId!,
          lines: state.lines,
          version: version,
          quotedPayablePaise: quote.quote.payablePaise,
        ),
      );
      state = ModifyState(result: result);
      _refresh();
    } on DioException catch (error) {
      state = _afterRejection(error, quote);
    } on Object catch (error) {
      state = state.copyWith(busy: false, error: describeApiError(error));
    }
  }

  void _refresh() {
    ref.invalidate(orderTrackingProvider(orderId));
    ref.invalidate(menuProvider);
    ref.invalidate(slotsProvider);
  }

  ModifyState _afterRejection(DioException error, ModificationQuoteOut quote) {
    final status = error.response?.statusCode;
    final data = error.response?.data;
    final detail = data is Map ? data['detail'] : null;
    // These answers are final for this attempt: drop the price and key.
    ModifyState refused(String message) {
      _refresh();
      return state.copyWith(
        busy: false,
        clearQuote: true,
        clearKey: true,
        error: message,
      );
    }

    if (status == 402) {
      return refused(
        'The extra amount could not be charged, so nothing was changed. '
        '$_unchanged',
      );
    }
    if (status == 409 && detail is Map) {
      final newQuote = detail['quote'];
      if (newQuote is Map<String, Object?>) {
        // FR-26: show the new price; confirming it is a new request.
        final price = QuoteOut.fromJson(newQuote);
        return state.copyWith(
          busy: false,
          quote: ModificationQuoteOut(
            quote: price,
            paidPaise: quote.paidPaise,
            differencePaise: price.payablePaise - quote.paidPaise,
          ),
          key: newIdempotencyKey(),
          error: 'The price changed. Check the new total and confirm again.',
        );
      }
      if (detail.containsKey('item_ids') || detail.containsKey('slot_id')) {
        return refused(unavailableMessage(ref, detail, _unchanged));
      }
      return refused(switch (detail['message']) {
        'the modification cut-off has passed' =>
          'It is too close to your pickup time to change this order.',
        'the order has changed' =>
          'The order changed while you were editing it. Review the change '
              'again.',
        _ => 'This order can no longer be changed. $_unchanged',
      });
    }
    if (status == 409 || status == 422) {
      return refused(describeApiError(error));
    }
    // A network failure or a busy server: confirming again repeats the same
    // request safely.
    return state.copyWith(busy: false, error: describeApiError(error));
  }
}

String _difference(int paise) {
  if (paise > 0) return 'You pay ${formatPaise(paise)} more.';
  if (paise < 0) return 'You get ${formatPaise(-paise)} back.';
  return 'The price stays the same.';
}

/// FR-35: change the items and/or slot of an order the kitchen has not started.
class ModifyOrderSection extends ConsumerWidget {
  const ModifyOrderSection(this.orderId, {super.key});

  final String orderId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final order = ref.watch(orderTrackingProvider(orderId)).value?.order;
    final modify = ref.watch(modifyOrderProvider(orderId));
    final controller = ref.read(modifyOrderProvider(orderId).notifier);
    final theme = Theme.of(context);
    final result = modify.result;
    final error = modify.error;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (result != null)
          Semantics(
            liveRegion: true,
            child: Text(_resultText(result), key: const Key('modify-result')),
          ),
        if (error != null)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Semantics(
              liveRegion: true,
              child: Text(
                error,
                key: const Key('modify-error'),
                style: TextStyle(color: theme.colorScheme.error),
              ),
            ),
          ),
        if (modify.editing)
          _Editor(orderId: orderId, state: modify, order: order)
        else if (order != null && order.status == OrderStatus.accepted)
          OutlinedButton(
            key: const Key('change-order'),
            onPressed: () => controller.start(order),
            child: const Text('Change order'),
          ),
      ],
    );
  }

  String _resultText(ModifiedOrderOut result) {
    final difference = result.differencePaise;
    if (difference > 0) {
      return 'Order changed. You paid ${formatPaise(difference)} more.';
    }
    final refund = result.refund;
    if (difference < 0 && refund != null) {
      return refund.status == PaymentStatus.pending
          ? 'Order changed. A refund of ${formatPaise(refund.amountPaise)} is '
                'on its way.'
          : 'Order changed. ${formatPaise(refund.amountPaise)} refunded.';
    }
    return 'Order changed. The price is the same.';
  }
}

class _Editor extends ConsumerWidget {
  const _Editor({required this.orderId, required this.state, this.order});

  final String orderId;
  final ModifyState state;
  final OrderDetailOut? order;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final controller = ref.read(modifyOrderProvider(orderId).notifier);
    final menu = ref.watch(menuProvider).value;
    final slots = ref.watch(slotsProvider).value;
    final theme = Theme.of(context);
    final quote = state.quote;
    return Card(
      key: const Key('modify-editor'),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Change your order', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            for (final item in menu?.items ?? <MenuItemOut>[])
              _ItemRow(orderId: orderId, item: item, state: state),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final slot in slots?.slots ?? <SlotAvailabilityOut>[])
                  ChoiceChip(
                    key: Key('mod-slot-${slot.id}'),
                    label: Text(formatSlot(slot.startsAt, slot.endsAt)),
                    selected: slot.id == state.slotId,
                    // The order's own seat stays available to it.
                    onSelected: slot.bookable || slot.id == state.heldSlotId
                        ? (_) => controller.selectSlot(slot.id)
                        : null,
                  ),
              ],
            ),
            const SizedBox(height: 12),
            if (quote != null) ...[
              Text(
                'New total ${formatPaise(quote.quote.payablePaise)}. '
                '${_difference(quote.differencePaise)}',
                key: const Key('modify-quote'),
              ),
              const SizedBox(height: 8),
              FilledButton(
                key: const Key('mod-confirm'),
                onPressed: state.busy || order == null
                    ? null
                    : () => controller.confirm(order!.version),
                child: Text(state.busy ? 'Saving…' : 'Confirm change'),
              ),
            ] else
              FilledButton(
                key: const Key('mod-review'),
                onPressed:
                    state.busy || state.quantities.isEmpty || !state.changed
                    ? null
                    : controller.review,
                child: Text(
                  state.busy ? 'Getting the price…' : 'Review change',
                ),
              ),
            TextButton(
              key: const Key('mod-discard'),
              onPressed: state.busy ? null : controller.discard,
              child: const Text('Discard changes'),
            ),
          ],
        ),
      ),
    );
  }
}

class _ItemRow extends ConsumerWidget {
  const _ItemRow({
    required this.orderId,
    required this.item,
    required this.state,
  });

  final String orderId;
  final MenuItemOut item;
  final ModifyState state;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final controller = ref.read(modifyOrderProvider(orderId).notifier);
    final quantity = state.quantities[item.id] ?? 0;
    final held = state.heldQuantities[item.id] ?? 0;
    final available = item.orderable ? item.availablePortions : 0;
    final most = available + held;
    return Row(
      children: [
        Expanded(child: Text('${item.name} · ${formatPaise(item.pricePaise)}')),
        IconButton(
          key: Key('mod-remove-${item.id}'),
          tooltip: 'Remove one ${item.name}',
          icon: const Icon(Icons.remove_circle_outline),
          onPressed: quantity == 0
              ? null
              : () => controller.setQuantity(item.id, quantity - 1),
        ),
        Text('$quantity', key: Key('mod-quantity-${item.id}')),
        IconButton(
          key: Key('mod-add-${item.id}'),
          tooltip: 'Add one ${item.name}',
          icon: const Icon(Icons.add_circle_outline),
          onPressed: quantity < most
              ? () => controller.setQuantity(item.id, quantity + 1)
              : null,
        ),
      ],
    );
  }
}
