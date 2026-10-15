import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api.dart';
import '../api/errors.dart';
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

  /// Fetch now, e.g. right after an order was moved, then poll as usual.
  Future<void> refresh() => _poll();
}

/// Kitchen Staff's screen: what to cook next (US-33), and the buttons that move
/// each order through Start, Ready, Picked Up and No-show (US-34).
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
            for (final slot in view.queue.earlierSlots)
              _SlotQueue(
                slot,
                key: ValueKey('ended-${slot.slotId}'),
                label: 'Ended · awaiting pickup',
                ended: true,
              ),
            for (final (index, slot) in view.queue.slots.indexed)
              _SlotQueue(
                slot,
                key: ValueKey(slot.slotId),
                label: index == 0 ? 'Current slot' : 'Next slot',
              ),
          ],
        ),
      ),
    );
  }
}

class _SlotQueue extends StatelessWidget {
  const _SlotQueue(
    this.slot, {
    super.key,
    required this.label,
    this.ended = false,
  });

  final SlotQueueOut slot;
  final String label;

  /// The slot is over, so a READY order may be marked no-show (after the grace).
  final bool ended;

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
            for (final order in slot.orders)
              _QueueOrder(order, key: ValueKey(order.id), slotEnded: ended),
          ],
        ),
      ),
    );
  }
}

class _QueueOrder extends ConsumerStatefulWidget {
  const _QueueOrder(this.order, {super.key, required this.slotEnded});

  final QueueOrderOut order;
  final bool slotEnded;

  @override
  ConsumerState<_QueueOrder> createState() => _QueueOrderState();
}

class _QueueOrderState extends ConsumerState<_QueueOrder> {
  bool _busy = false;
  String? _error;

  QueueOrderOut get _order => widget.order;

  /// FR-43: the moves the kitchen can make from the order's state.
  List<(KitchenAction, String)> get _actions => switch (_order.status) {
    OrderStatus.accepted => [(KitchenAction.start, 'Start')],
    OrderStatus.preparing => [(KitchenAction.ready, 'Mark ready')],
    OrderStatus.ready => [
      (KitchenAction.pickedUp, 'Picked up'),
      if (widget.slotEnded) (KitchenAction.noShow, 'No-show'),
    ],
    _ => [],
  };

  Future<void> _move(KitchenAction action) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    String? error;
    try {
      await ref
          .read(apiProvider)
          .kitchen
          .transitionKitchenOrder(
            orderId: _order.id,
            body: TransitionRequest(action: action),
          );
    } on Object catch (failure) {
      error = _transitionError(failure);
    }
    // Show the order's real state either way: moved, or moved by someone else.
    await ref.read(kitchenQueueProvider.notifier).refresh();
    if (mounted) {
      setState(() {
        _busy = false;
        _error = error;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final id = _order.id;
    final items = _order.lines.map((l) => '${l.name} × ${l.qty}').join(', ');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ListTile(
          key: Key('queue-order-$id'),
          contentPadding: EdgeInsets.zero,
          title: Text(items),
          subtitle: Text(
            'Order …${_short(id)} · confirmed '
            '${formatIstTime(_order.confirmedAt)}',
          ),
          trailing: Chip(label: Text(_statusLabel(_order.status))),
        ),
        Wrap(
          spacing: 8,
          children: [
            for (final (action, label) in _actions)
              OutlinedButton(
                key: Key('${action.json}-$id'),
                onPressed: _busy ? null : () => _move(action),
                child: Text(label),
              ),
          ],
        ),
        if (_error case final error?)
          FormMessage(error, key: Key('order-error-$id'), isError: true),
        const Divider(),
      ],
    );
  }
}

/// A 409 says why the move was refused; a too-early no-show says from when.
String _transitionError(Object error) {
  if (error is DioException && error.response?.statusCode == 409) {
    final data = error.response?.data;
    final detail = data is Map ? data['detail'] : null;
    final allowedFrom = detail is Map
        ? DateTime.tryParse('${detail['allowed_from']}')
        : null;
    if (allowedFrom != null) {
      return 'Too early for a no-show: allowed from '
          '${formatIstTime(allowedFrom)}.';
    }
    final status = detail is Map ? detail['status'] : null;
    if (status != null) {
      return 'Not changed: the order is already $status.';
    }
  }
  return describeApiError(error);
}

/// The last characters of an order ID, enough to match a Student's screen.
String _short(String id) => id.length <= 6 ? id : id.substring(id.length - 6);

String _statusLabel(OrderStatus status) => switch (status) {
  OrderStatus.accepted => 'Accepted',
  OrderStatus.preparing => 'Preparing',
  OrderStatus.ready => 'Ready',
  _ => status.name,
};
