import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api.dart';
import '../api/errors.dart';
import 'format.dart';

/// P-POLL: how often an order that is not finished is refreshed (FR-40).
final pollIntervalProvider = Provider<Duration>(
  (ref) => const Duration(seconds: 10),
);

const _finished = {
  OrderStatus.pickedUp,
  OrderStatus.noShow,
  OrderStatus.cancelled,
  OrderStatus.paymentFailed,
};

bool isFinished(OrderStatus status) => _finished.contains(status);

/// The latest known state of one order, plus whether the last refresh failed.
class TrackedOrder {
  const TrackedOrder(this.order, {this.refreshFailed = false});

  final OrderDetailOut order;
  final bool refreshFailed;
}

/// One order, refreshed every P-POLL until it reaches a final state. A failed
/// refresh keeps the last known state on screen and tries again next time.
final orderTrackingProvider = AsyncNotifierProvider.autoDispose
    .family<OrderTracker, TrackedOrder, String>(
      OrderTracker.new,
      retry: (_, _) => null,
    );

class OrderTracker extends AsyncNotifier<TrackedOrder> {
  OrderTracker(this.orderId);

  final String orderId;
  Timer? _timer;

  @override
  Future<TrackedOrder> build() async {
    // Poll only while the order is on screen.
    ref.onCancel(() => _timer?.cancel());
    ref.onResume(() {
      final last = state.value;
      if (last != null) _scheduleNext(last.order);
    });
    ref.onDispose(() => _timer?.cancel());
    final tracked = TrackedOrder(await _fetch());
    _scheduleNext(tracked.order);
    return tracked;
  }

  Future<OrderDetailOut> _fetch() {
    return ref.read(apiProvider).ordering.getOrder(orderId: orderId);
  }

  void _scheduleNext(OrderDetailOut order) {
    _timer?.cancel();
    if (isFinished(order.status)) return;
    _timer = Timer(ref.read(pollIntervalProvider), _poll);
  }

  Future<void> _poll() async {
    final last = state.value;
    try {
      final order = await _fetch();
      state = AsyncData(TrackedOrder(order));
      _scheduleNext(order);
    } on Object catch (error, stack) {
      if (last == null) {
        state = AsyncError(error, stack);
        return;
      }
      state = AsyncData(TrackedOrder(last.order, refreshFailed: true));
      _scheduleNext(last.order);
    }
  }
}

String _headline(OrderStatus status) {
  return switch (status) {
    OrderStatus.pendingPayment => 'Waiting for the payment to go through.',
    OrderStatus.accepted => 'Confirmed. The kitchen has not started it yet.',
    OrderStatus.preparing => 'Being prepared.',
    OrderStatus.ready => 'Ready. Collect it during your pickup slot.',
    OrderStatus.pickedUp => 'Picked up. Enjoy your meal.',
    OrderStatus.noShow => 'Not collected in time.',
    OrderStatus.cancelled => 'Cancelled.',
    OrderStatus.paymentFailed => 'The payment did not go through.',
    OrderStatus.$unknown => 'Status updated.',
  };
}

String _step(TransitionOut step) {
  final what = switch (step.toStatus) {
    OrderStatus.pendingPayment => 'Order placed',
    OrderStatus.accepted => 'Payment confirmed',
    OrderStatus.preparing => 'Preparation started',
    OrderStatus.ready => 'Ready for pickup',
    OrderStatus.pickedUp => 'Picked up',
    OrderStatus.noShow => 'Marked as not collected',
    OrderStatus.cancelled => 'Cancelled',
    OrderStatus.paymentFailed => 'Payment failed',
    OrderStatus.$unknown => 'Status changed',
  };
  final by = switch (step.actorRole) {
    Role.kitchen => ' by the kitchen',
    Role.admin => ' by the cafeteria',
    _ => '',
  };
  return '$what$by';
}

/// FR-40: the order's current state and its timestamped history, kept up to
/// date while the order is not finished.
class OrderStatusPanel extends ConsumerWidget {
  const OrderStatusPanel(this.orderId, {super.key});

  final String orderId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tracked = ref.watch(orderTrackingProvider(orderId));
    final theme = Theme.of(context);
    return tracked.when(
      skipLoadingOnRefresh: true,
      skipLoadingOnReload: true,
      loading: () => const Padding(
        padding: EdgeInsets.all(16),
        child: Center(child: CircularProgressIndicator()),
      ),
      error: (error, _) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Could not load the order status. ${describeApiError(error)}'),
          TextButton(
            onPressed: () => ref.invalidate(orderTrackingProvider(orderId)),
            child: const Text('Try again'),
          ),
        ],
      ),
      data: (tracked) {
        final order = tracked.order;
        return Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Semantics(
                  liveRegion: true,
                  child: Text(
                    _headline(order.status),
                    key: const Key('order-status'),
                    style: theme.textTheme.titleMedium,
                  ),
                ),
                if (tracked.refreshFailed)
                  Text(
                    'Could not refresh the status; trying again shortly.',
                    style: TextStyle(color: theme.colorScheme.error),
                  ),
                const SizedBox(height: 8),
                for (final step in order.history)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 2),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        SizedBox(
                          width: 56,
                          child: Text(formatIstTime(step.at)),
                        ),
                        Expanded(child: Text(_step(step))),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        );
      },
    );
  }
}
