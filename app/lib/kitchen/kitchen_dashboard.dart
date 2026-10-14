import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api.dart';
import '../dashboards/common.dart';
import '../dashboards/dashboard_scaffold.dart';
import '../student/format.dart';
import '../student/order_tracking.dart' show pollIntervalProvider;

/// The latest queue, plus whether the last refresh failed.
class QueueView {
  const QueueView(this.queue, {this.refreshFailed = false});

  final KitchenQueueOut queue;
  final bool refreshFailed;
}

/// FR-42: the current and next slot's orders, refreshed every P-POLL while the
/// screen is open. A failed refresh keeps the last queue on screen.
final kitchenQueueProvider =
    AsyncNotifierProvider.autoDispose<KitchenQueue, QueueView>(
      KitchenQueue.new,
      retry: (_, _) => null,
    );

class KitchenQueue extends AsyncNotifier<QueueView> {
  Timer? _timer;

  @override
  Future<QueueView> build() async {
    // Poll only while the queue is on screen.
    ref.onCancel(() => _timer?.cancel());
    ref.onResume(_schedule);
    ref.onDispose(() => _timer?.cancel());
    final view = QueueView(await _fetch());
    _schedule();
    return view;
  }

  Future<KitchenQueueOut> _fetch() =>
      ref.read(apiProvider).kitchen.getKitchenQueue();

  void _schedule() {
    _timer?.cancel();
    _timer = Timer(ref.read(pollIntervalProvider), _poll);
  }

  Future<void> _poll() async {
    final last = state.value;
    try {
      state = AsyncData(QueueView(await _fetch()));
    } on Object catch (error, stack) {
      state = last == null
          ? AsyncError(error, stack)
          : AsyncData(QueueView(last.queue, refreshFailed: true));
    }
    _schedule();
  }
}

/// Kitchen Staff's screen: what to cook next (US-33). The buttons that move an
/// order through Start, Ready, Picked Up and No-show arrive with CAFIITK-159.
class KitchenDashboard extends ConsumerWidget {
  const KitchenDashboard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return DashboardScaffold(
      title: 'Kitchen',
      body: Loaded(
        value: ref.watch(kitchenQueueProvider),
        onRetry: () => ref.invalidate(kitchenQueueProvider),
        builder: (view) => ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (view.refreshFailed)
              const FormMessage(
                'Could not refresh the queue; showing the last one received.',
                key: Key('queue-stale'),
                isError: true,
              ),
            if (view.queue.slots.isEmpty)
              const Text(
                'No more pickup slots today.',
                key: Key('queue-empty'),
              ),
            for (final (index, slot) in view.queue.slots.indexed)
              _SlotQueue(
                slot,
                label: index == 0 ? 'Current slot' : 'Next slot',
              ),
          ],
        ),
      ),
    );
  }
}

class _SlotQueue extends StatelessWidget {
  const _SlotQueue(this.slot, {required this.label});

  final SlotQueueOut slot;
  final String label;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final byPriority = slot.totalsOrder == TotalsOrder.prepPriority;
    return Card(
      key: Key('queue-slot-${slot.slotId}'),
      margin: const EdgeInsets.only(bottom: 16),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SectionHeading(
              '$label · ${formatSlot(slot.startsAt, slot.endsAt)}',
            ),
            Text('To prepare', style: theme.textTheme.titleMedium),
            Text(
              byPriority
                  ? 'In the order the Administrator approved'
                  : 'Most portions first',
              key: Key('totals-order-${slot.slotId}'),
              style: theme.textTheme.bodySmall,
            ),
            if (slot.itemTotals.isEmpty)
              const Text('Nothing left to prepare.')
            else
              for (final (index, line) in slot.itemTotals.indexed)
                Text(
                  '${index + 1}. ${line.name} × ${line.qty}',
                  key: Key('total-${slot.slotId}-${line.itemId}'),
                ),
            const SizedBox(height: 12),
            Text(
              'Orders (${slot.orders.length})',
              style: theme.textTheme.titleMedium,
            ),
            if (slot.orders.isEmpty) const Text('No orders in this slot.'),
            for (final order in slot.orders) _QueueOrder(order),
          ],
        ),
      ),
    );
  }
}

class _QueueOrder extends StatelessWidget {
  const _QueueOrder(this.order);

  final QueueOrderOut order;

  @override
  Widget build(BuildContext context) {
    final items = order.lines.map((l) => '${l.name} × ${l.qty}').join(', ');
    return ListTile(
      key: Key('queue-order-${order.id}'),
      contentPadding: EdgeInsets.zero,
      title: Text(items),
      subtitle: Text(
        'Order …${_short(order.id)} · confirmed '
        '${formatIstTime(order.confirmedAt)}',
      ),
      trailing: Chip(label: Text(_statusLabel(order.status))),
    );
  }
}

/// The last characters of an order ID, enough to match a Student's screen.
String _short(String id) => id.length <= 6 ? id : id.substring(id.length - 6);

String _statusLabel(OrderStatus status) => switch (status) {
  OrderStatus.accepted => 'Accepted',
  OrderStatus.preparing => 'Preparing',
  OrderStatus.ready => 'Ready',
  _ => status.name,
};
