import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api.dart';
import '../dashboards/common.dart';
import '../student/format.dart';
import '../student/order_tracking.dart' show pollIntervalProvider;
import '../theme.dart';
import 'admin_state.dart';

/// What the Administrator filters today's orders by (FR-45). Null means any.
typedef OrderFilter = ({String? slotId, OrderStatus? status, String? student});

final orderFilterProvider =
    NotifierProvider.autoDispose<OrderFilterState, OrderFilter>(
      OrderFilterState.new,
    );

class OrderFilterState extends Notifier<OrderFilter> {
  @override
  OrderFilter build() => (slotId: null, status: null, student: null);

  void set(OrderFilter filter) => state = filter;
}

/// FR-45: today's orders matching the filter, by slot time.
final dayOrdersProvider = FutureProvider.autoDispose<List<AdminOrderOut>>((
  ref,
) {
  final filter = ref.watch(orderFilterProvider);
  return ref
      .watch(apiProvider)
      .ordering
      .listDayOrders(
        date: istToday(),
        slotId: filter.slotId,
        status: filter.status == null ? null : [filter.status!],
        student: filter.student,
      );
}, retry: (_, _) => null);

String orderStatusLabel(OrderStatus status) => switch (status) {
  OrderStatus.pendingPayment => 'Pending payment',
  OrderStatus.accepted => 'Accepted',
  OrderStatus.preparing => 'Preparing',
  OrderStatus.ready => 'Ready',
  OrderStatus.pickedUp => 'Picked up',
  OrderStatus.noShow => 'No-show',
  OrderStatus.cancelled => 'Cancelled',
  OrderStatus.paymentFailed => 'Payment failed',
  OrderStatus.$unknown => 'Unknown',
};

/// US-37 AC1: today's orders, filtered by slot, state and Student.
class OrdersTab extends ConsumerStatefulWidget {
  const OrdersTab({super.key});

  @override
  ConsumerState<OrdersTab> createState() => _OrdersTabState();
}

class _OrdersTabState extends ConsumerState<OrdersTab> {
  final _student = TextEditingController();

  @override
  void dispose() {
    _student.dispose();
    super.dispose();
  }

  OrderFilter get _filter => ref.read(orderFilterProvider);

  void _set(OrderFilter filter) =>
      ref.read(orderFilterProvider.notifier).set(filter);

  void _searchStudent() {
    final text = _student.text.trim();
    _set((
      slotId: _filter.slotId,
      status: _filter.status,
      student: text.isEmpty ? null : text,
    ));
  }

  @override
  Widget build(BuildContext context) {
    final filter = ref.watch(orderFilterProvider);
    final slots = ref.watch(adminSlotsProvider(istToday())).value?.slots;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const SectionHeading("Today's orders"),
        Wrap(
          spacing: 16,
          runSpacing: 8,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            FieldFrame(
              child: DropdownButton<String?>(
                key: const Key('filter-slot'),
                value: filter.slotId,
                hint: const Text('Any slot'),
                onChanged: (slotId) => _set((
                  slotId: slotId,
                  status: filter.status,
                  student: filter.student,
                )),
                items: [
                  const DropdownMenuItem(value: null, child: Text('Any slot')),
                  for (final slot in slots ?? const <SlotAvailabilityOut>[])
                    DropdownMenuItem(
                      key: Key('filter-slot-${slot.id}'),
                      value: slot.id,
                      child: Text(formatSlot(slot.startsAt, slot.endsAt)),
                    ),
                ],
              ),
            ),
            FieldFrame(
              child: DropdownButton<OrderStatus?>(
                key: const Key('filter-status'),
                value: filter.status,
                hint: const Text('Any state'),
                onChanged: (status) => _set((
                  slotId: filter.slotId,
                  status: status,
                  student: filter.student,
                )),
                items: [
                  const DropdownMenuItem(value: null, child: Text('Any state')),
                  for (final status in OrderStatus.values)
                    if (status != OrderStatus.$unknown)
                      DropdownMenuItem(
                        key: Key('filter-status-${status.json}'),
                        value: status,
                        child: Text(orderStatusLabel(status)),
                      ),
                ],
              ),
            ),
            SizedBox(
              width: 260,
              child: TextField(
                key: const Key('filter-student'),
                controller: _student,
                decoration: InputDecoration(
                  labelText: 'Student name or email',
                  suffixIcon: IconButton(
                    key: const Key('filter-student-search'),
                    tooltip: 'Search',
                    icon: const Icon(Icons.search),
                    onPressed: _searchStudent,
                  ),
                ),
                onSubmitted: (_) => _searchStudent(),
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        Loaded(
          value: ref.watch(dayOrdersProvider),
          onRetry: () => ref.invalidate(dayOrdersProvider),
          builder: (orders) => orders.isEmpty
              ? const Text(
                  'No orders match these filters.',
                  key: Key('orders-empty'),
                )
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      '${orders.length} '
                      '${orders.length == 1 ? 'order' : 'orders'}',
                      key: const Key('orders-count'),
                    ),
                    for (final order in orders) _AdminOrderTile(order),
                  ],
                ),
        ),
      ],
    );
  }
}

class _AdminOrderTile extends StatelessWidget {
  const _AdminOrderTile(this.order);

  final AdminOrderOut order;

  @override
  Widget build(BuildContext context) {
    final lines = order.price.lines
        .map((line) => '${line.name} × ${line.qty}')
        .join(', ');
    return Card(
      key: Key('admin-order-${order.id}'),
      child: ListTile(
        title: Text(
          '${formatIstTime(order.slotStartsAt)} · ${order.studentName}',
        ),
        subtitle: Text(
          '${order.studentEmail}\n$lines · '
          '${formatPaise(order.price.payablePaise)}',
        ),
        isThreeLine: true,
        trailing: Chip(
          key: Key('admin-order-status-${order.id}'),
          label: Text(orderStatusLabel(order.status)),
        ),
      ),
    );
  }
}

/// The latest utilisation, plus whether the last refresh failed.
class UtilisationView {
  const UtilisationView(this.utilisation, {this.refreshFailed = false});

  final UtilisationOut utilisation;
  final bool refreshFailed;
}

/// FR-46: today's utilisation, refreshed every P-POLL (within the 30 s US-37
/// AC2 allows) while the tab is open. A failed refresh keeps the last figures.
final utilisationProvider =
    AsyncNotifierProvider.autoDispose<Utilisation, UtilisationView>(
      Utilisation.new,
      retry: (_, _) => null,
    );

class Utilisation extends AsyncNotifier<UtilisationView> {
  Timer? _timer;

  @override
  Future<UtilisationView> build() async {
    // Poll only while the view is on screen.
    ref.onCancel(() => _timer?.cancel());
    ref.onResume(_schedule);
    ref.onDispose(() => _timer?.cancel());
    final view = UtilisationView(await _fetch());
    _schedule();
    return view;
  }

  Future<UtilisationOut> _fetch() =>
      ref.read(apiProvider).ordering.getUtilisation(date: istToday());

  void _schedule() {
    _timer?.cancel();
    _timer = Timer(ref.read(pollIntervalProvider), _poll);
  }

  Future<void> _poll() async {
    final last = state.value;
    try {
      state = AsyncData(UtilisationView(await _fetch()));
    } on Object catch (error, stack) {
      state = last == null
          ? AsyncError(error, stack)
          : AsyncData(UtilisationView(last.utilisation, refreshFailed: true));
    }
    _schedule();
  }
}

/// US-37 AC2: how full each slot and item is today, and orders per state.
class UtilisationTab extends ConsumerWidget {
  const UtilisationTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Loaded(
      value: ref.watch(utilisationProvider),
      onRetry: () => ref.invalidate(utilisationProvider),
      builder: (view) {
        final u = view.utilisation;
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text(
              'As of ${formatIstTime(u.asOf)} · refreshes automatically',
              key: const Key('utilisation-as-of'),
            ),
            if (view.refreshFailed)
              const FormMessage(
                'Could not refresh; showing the last figures received.',
                key: Key('utilisation-stale'),
                isError: true,
              ),
            const SizedBox(height: 16),
            const SectionHeading('Orders by state'),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final status in OrderStatus.values)
                  if (status != OrderStatus.$unknown)
                    Chip(
                      key: Key('count-${status.json}'),
                      label: Text(
                        '${orderStatusLabel(status)}: '
                        '${u.orderCounts[status.json] ?? 0}',
                      ),
                    ),
              ],
            ),
            const SizedBox(height: 16),
            const SectionHeading('Pickup slots'),
            if (u.slots.isEmpty)
              const Text('No pickup slots are configured for today.'),
            for (final slot in u.slots)
              _Fill(
                key: Key('util-slot-${slot.slotId}'),
                label: formatSlot(slot.startsAt, slot.endsAt),
                figure: '${slot.booked}/${slot.capacity} seats booked',
                used: slot.booked,
                of: slot.capacity,
              ),
            const SizedBox(height: 16),
            const SectionHeading('Portions'),
            for (final item in u.items)
              _Fill(
                key: Key('util-item-${item.itemId}'),
                label: item.name,
                figure:
                    '${item.allocated}/${item.total} allocated · '
                    '${item.available} left',
                used: item.allocated,
                of: item.total,
              ),
          ],
        );
      },
    );
  }
}

class _Fill extends StatelessWidget {
  const _Fill({
    super.key,
    required this.label,
    required this.figure,
    required this.used,
    required this.of,
  });

  final String label;
  final String figure;
  final int used;
  final int of;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('$label · $figure'),
          const SizedBox(height: 4),
          LinearProgressIndicator(
            value: of == 0 ? 0 : used / of,
            semanticsLabel: '$label, $figure',
          ),
        ],
      ),
    );
  }
}
