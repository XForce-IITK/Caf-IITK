import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../api/api.dart';
import '../api/errors.dart';
import '../dashboards/dashboard_scaffold.dart';
import 'format.dart';
import 'order_tracking.dart';

const myOrdersPath = '/student/orders';

String orderPath(String orderId) => '$myOrdersPath/$orderId';

/// FR-28: the Student's own orders, newest first, each at its latest price.
final myOrdersProvider = FutureProvider.autoDispose<List<OrderOut>>(
  (ref) => ref.read(apiProvider).ordering.listMyOrders(),
  retry: (_, _) => null,
);

String statusLabel(OrderStatus status) {
  return switch (status) {
    OrderStatus.pendingPayment => 'Awaiting payment',
    OrderStatus.accepted => 'Confirmed',
    OrderStatus.preparing => 'Being prepared',
    OrderStatus.ready => 'Ready',
    OrderStatus.pickedUp => 'Picked up',
    OrderStatus.noShow => 'Not collected',
    OrderStatus.cancelled => 'Cancelled',
    OrderStatus.paymentFailed => 'Payment failed',
    OrderStatus.$unknown => 'Unknown',
  };
}

class MyOrdersScreen extends ConsumerWidget {
  const MyOrdersScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final orders = ref.watch(myOrdersProvider);
    return DashboardScaffold(
      title: 'My orders',
      body: _Centred(
        children: [
          TextButton.icon(
            key: const Key('back-to-menu'),
            onPressed: () => context.go('/student'),
            icon: const Icon(Icons.arrow_back),
            label: const Text('Back to the menu'),
          ),
          orders.when(
            skipLoadingOnRefresh: true,
            loading: () => const Padding(
              padding: EdgeInsets.all(24),
              child: Center(child: CircularProgressIndicator()),
            ),
            error: (error, _) => Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(describeApiError(error)),
                TextButton(
                  onPressed: () => ref.invalidate(myOrdersProvider),
                  child: const Text('Try again'),
                ),
              ],
            ),
            data: (orders) => orders.isEmpty
                ? const Text('You have not placed any orders yet.')
                : Column(
                    children: [for (final order in orders) _OrderTile(order)],
                  ),
          ),
        ],
      ),
    );
  }
}

class _OrderTile extends StatelessWidget {
  const _OrderTile(this.order);

  final OrderOut order;

  @override
  Widget build(BuildContext context) {
    final items = order.price.lines
        .map((line) => '${line.qty} × ${line.name}')
        .join(', ');
    return Card(
      child: ListTile(
        key: Key('order-${order.id}'),
        title: Text(items),
        subtitle: Text(
          '${formatIstDate(order.createdAt)} '
          '${formatIstTime(order.createdAt)} · ${statusLabel(order.status)}',
        ),
        trailing: Text(formatPaise(order.price.payablePaise)),
        onTap: () => context.go(orderPath(order.id)),
      ),
    );
  }
}

/// FR-28, UC-14: one order's status and history, every price snapshot version
/// as it was shown, and every refund.
class OrderHistoryScreen extends ConsumerWidget {
  const OrderHistoryScreen(this.orderId, {super.key});

  final String orderId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final order = ref.watch(orderTrackingProvider(orderId)).value?.order;
    final theme = Theme.of(context);
    return DashboardScaffold(
      title: 'Order',
      body: _Centred(
        children: [
          TextButton.icon(
            key: const Key('back-to-orders'),
            onPressed: () => context.go(myOrdersPath),
            icon: const Icon(Icons.arrow_back),
            label: const Text('My orders'),
          ),
          OrderStatusPanel(orderId),
          if (order != null) ...[
            const SizedBox(height: 16),
            Semantics(
              header: true,
              child: Text('Price history', style: theme.textTheme.titleLarge),
            ),
            for (final snapshot in order.snapshots.reversed)
              _SnapshotCard(
                snapshot,
                isLatest: snapshot == order.snapshots.last,
              ),
            const SizedBox(height: 16),
            Semantics(
              header: true,
              child: Text('Refunds', style: theme.textTheme.titleLarge),
            ),
            if (order.refunds.isEmpty)
              const Text('No refunds on this order.', key: Key('no-refunds'))
            else
              for (final refund in order.refunds) _RefundRow(refund),
          ],
        ],
      ),
    );
  }
}

class _SnapshotCard extends StatelessWidget {
  const _SnapshotCard(this.snapshot, {required this.isLatest});

  final SnapshotOut snapshot;
  final bool isLatest;

  @override
  Widget build(BuildContext context) {
    final price = snapshot.price;
    final bold = Theme.of(context).textTheme.titleMedium;
    final when =
        '${formatIstDate(snapshot.pricedAt)} ${formatIstTime(snapshot.pricedAt)}';
    return Card(
      key: Key('snapshot-v${snapshot.version}'),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Version ${snapshot.version}${isLatest ? ' (current)' : ''} · '
              'priced $when',
              style: bold,
            ),
            const SizedBox(height: 4),
            for (final line in price.lines) ...[
              _Amount('${line.qty} × ${line.name}', line.lineBasePaise),
              if (line.lineDiscountPaise > 0)
                _Amount(
                  '  Discount ${line.discountPct}%',
                  -line.lineDiscountPaise,
                ),
            ],
            const Divider(),
            _Amount('Subtotal', price.discountedSubtotalPaise),
            if (price.subsidyPaise > 0) _Amount('Subsidy', -price.subsidyPaise),
            if (price.roundingAdjustmentPaise != 0)
              _Amount('Rounding', price.roundingAdjustmentPaise),
            _Amount('To pay', price.payablePaise, style: bold),
          ],
        ),
      ),
    );
  }
}

class _RefundRow extends StatelessWidget {
  const _RefundRow(this.refund);

  final OrderRefundOut refund;

  @override
  Widget build(BuildContext context) {
    final why = switch (refund.cause) {
      PaymentCause.cancel => 'cancellation',
      PaymentCause.modify => 'change to a cheaper order',
      _ => 'refund',
    };
    final state = switch (refund.status) {
      PaymentStatus.pending => ' · on its way',
      PaymentStatus.failed => ' · failed, being retried',
      _ => '',
    };
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Text(
        '${formatPaise(refund.amountPaise)} refunded for the $why on '
        '${formatIstDate(refund.at)} at ${formatIstTime(refund.at)}$state',
        key: const Key('refund'),
      ),
    );
  }
}

class _Amount extends StatelessWidget {
  const _Amount(this.label, this.paise, {this.style});

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

class _Centred extends StatelessWidget {
  const _Centred({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.topCenter,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 720),
        child: ListView(padding: const EdgeInsets.all(16), children: children),
      ),
    );
  }
}
