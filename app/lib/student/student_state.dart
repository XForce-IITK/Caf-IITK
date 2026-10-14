import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api.dart';
import '../api/errors.dart';
import 'format.dart';

/// Today's menu with what is left of each item (FR-13). A failed load is shown
/// with a retry button rather than retried silently.
final menuProvider = FutureProvider.autoDispose<MenuOut>(
  (ref) => ref.watch(apiProvider).catalogue.browseMenu(),
  retry: (_, _) => null,
);

/// Today's pickup slots with their remaining seats (FR-19).
final slotsProvider = FutureProvider.autoDispose<SlotListOut>(
  (ref) => ref.watch(apiProvider).slots.browseSlots(),
  retry: (_, _) => null,
);

/// What the Student has picked so far: a quantity per item and one slot.
class Cart {
  const Cart({this.quantities = const {}, this.slotId});

  final Map<String, int> quantities;
  final String? slotId;

  int quantityOf(String itemId) => quantities[itemId] ?? 0;

  bool get isReady => quantities.isNotEmpty && slotId != null;

  List<QuoteLineIn> get lines => [
    for (final entry in quantities.entries)
      QuoteLineIn(itemId: entry.key, qty: entry.value),
  ];
}

final cartProvider = NotifierProvider.autoDispose<CartController, Cart>(
  CartController.new,
);

class CartController extends Notifier<Cart> {
  @override
  Cart build() => const Cart();

  void setQuantity(String itemId, int quantity) {
    final quantities = Map.of(state.quantities);
    if (quantity <= 0) {
      quantities.remove(itemId);
    } else {
      quantities[itemId] = quantity;
    }
    state = Cart(quantities: quantities, slotId: state.slotId);
  }

  void selectSlot(String slotId) {
    state = Cart(quantities: state.quantities, slotId: slotId);
  }

  void clear() => state = const Cart();
}

/// Where the Student is between reviewing the price and holding an order.
class Checkout {
  const Checkout({
    this.quote,
    this.idempotencyKey,
    this.busy = false,
    this.error,
    this.order,
  });

  /// The price the Student is looking at; null until they ask to review.
  final QuoteOut? quote;

  /// One key per confirmation of [quote], reused if that confirmation is
  /// repeated (NFR-18). A new quote gets a new key.
  final String? idempotencyKey;
  final bool busy;
  final String? error;

  /// The accepted order, once there is one.
  final OrderOut? order;
}

final checkoutProvider =
    NotifierProvider.autoDispose<CheckoutController, Checkout>(
      CheckoutController.new,
    );

class CheckoutController extends Notifier<Checkout> {
  @override
  Checkout build() {
    // A quote is only valid for the cart it was made for.
    ref.listen(cartProvider, (_, _) => state = Checkout(order: state.order));
    return const Checkout();
  }

  CafApi get _api => ref.read(apiProvider);

  /// FR-25: price the cart for the chosen slot. Reserves nothing.
  Future<void> review() async {
    final cart = ref.read(cartProvider);
    if (!cart.isReady || state.busy) return;
    state = const Checkout(busy: true);
    try {
      final quote = await _api.pricing.createQuote(
        body: QuoteRequest(slotId: cart.slotId!, lines: cart.lines),
      );
      state = Checkout(quote: quote, idempotencyKey: newIdempotencyKey());
    } on Object catch (error) {
      state = Checkout(error: describeApiError(error));
    }
  }

  /// FR-30: place the order at the price being shown.
  Future<void> confirm() async {
    final quote = state.quote;
    final key = state.idempotencyKey;
    final cart = ref.read(cartProvider);
    if (quote == null || key == null || state.busy) return;
    state = Checkout(quote: quote, idempotencyKey: key, busy: true);
    try {
      final order = await _api.ordering.placeOrder(
        idempotencyKey: key,
        body: PlaceOrderRequest(
          slotId: cart.slotId!,
          lines: cart.lines,
          quotedPayablePaise: quote.payablePaise,
        ),
      );
      _refreshAvailability();
      if (order.status == OrderStatus.paymentFailed) {
        state = const Checkout(
          error:
              'The payment did not go through, so nothing was charged and '
              'nothing is reserved. Review the order to try again.',
        );
        return;
      }
      state = Checkout(order: order);
      ref.read(cartProvider.notifier).clear();
    } on DioException catch (error) {
      state = _afterRejection(error, quote, key);
    } on Object catch (error) {
      state = Checkout(
        quote: quote,
        idempotencyKey: key,
        error: describeApiError(error),
      );
    }
  }

  /// Start over after an order has been placed.
  void placeAnother() {
    state = const Checkout();
    _refreshAvailability();
  }

  void _refreshAvailability() {
    ref.invalidate(menuProvider);
    ref.invalidate(slotsProvider);
  }

  Checkout _afterRejection(DioException error, QuoteOut quote, String key) {
    final data = error.response?.data;
    final detail = data is Map ? data['detail'] : null;
    if (error.response?.statusCode == 409 && detail is Map) {
      final newQuote = detail['quote'];
      if (newQuote is Map<String, Object?>) {
        // FR-26: never charge an amount the Student has not seen.
        return Checkout(
          quote: QuoteOut.fromJson(newQuote),
          idempotencyKey: newIdempotencyKey(),
          error: 'The price changed. Check the new total and confirm again.',
        );
      }
      if (detail.containsKey('item_ids') || detail.containsKey('slot_id')) {
        final message = _unavailableMessage(detail);
        _refreshAvailability();
        return Checkout(error: message);
      }
      final opensAt = DateTime.tryParse('${detail['opens_at']}');
      if (opensAt != null) {
        return Checkout(error: 'Ordering opens at ${formatIstTime(opensAt)}.');
      }
    }
    // Anything else leaves the quote and key in place, so pressing Confirm
    // again repeats the same request safely.
    return Checkout(
      quote: quote,
      idempotencyKey: key,
      error: describeApiError(error),
    );
  }

  /// NFR-32: say exactly which item(s) or slot could not be had.
  String _unavailableMessage(Map<dynamic, dynamic> detail) {
    final menu = ref.read(menuProvider).value;
    final slots = ref.read(slotsProvider).value;
    final itemIds = detail['item_ids'];
    final names = [
      if (itemIds is List)
        for (final id in itemIds)
          menu?.items.where((item) => item.id == id).firstOrNull?.name ??
              'an item',
    ];
    final slotId = detail['slot_id'];
    final slot = slots?.slots.where((slot) => slot.id == slotId).firstOrNull;
    final parts = [
      if (names.isNotEmpty) 'No longer available: ${names.join(', ')}.',
      if (slotId != null)
        slot == null
            ? 'The pickup slot is no longer available.'
            : 'The ${formatSlot(slot.startsAt, slot.endsAt)} slot is no '
                  'longer available.',
    ];
    return '${parts.join(' ')} Nothing was reserved or charged.';
  }
}
