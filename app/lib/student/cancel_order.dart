import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api.dart';
import '../api/errors.dart';
import 'format.dart';
import 'order_tracking.dart';

/// A Student may cancel from these states, before the cut-off (FR-37). The
/// server decides the cut-off; the client only offers the button.
const _cancellable = {OrderStatus.accepted, OrderStatus.preparing};

class CancelState {
  const CancelState({this.busy = false, this.error, this.refund, this.key});

  final bool busy;
  final String? error;

  /// The refund, once the order is cancelled.
  final RefundOut? refund;

  /// The idempotency key of a cancel that has not finished, reused if the
  /// Student presses Cancel again (NFR-18). Cleared once the server decides.
  final String? key;
}

final cancelOrderProvider = NotifierProvider.autoDispose
    .family<CancelController, CancelState, String>(CancelController.new);

class CancelController extends Notifier<CancelState> {
  CancelController(this.orderId);

  final String orderId;

  @override
  CancelState build() => const CancelState();

  /// FR-37: cancel at [version], the order version the Student is looking at.
  Future<void> cancel(int version) async {
    if (state.busy) return;
    final key = state.key ?? newIdempotencyKey();
    state = CancelState(busy: true, key: key);
    try {
      final cancelled = await ref
          .read(apiProvider)
          .ordering
          .cancelOrder(
            orderId: orderId,
            idempotencyKey: key,
            body: CancelOrderRequest(version: version),
          );
      state = CancelState(refund: cancelled.refund);
      ref.invalidate(orderTrackingProvider(orderId));
    } on DioException catch (error) {
      state = _afterRejection(error, key);
    } on Object catch (error) {
      state = CancelState(error: describeApiError(error), key: key);
    }
  }

  CancelState _afterRejection(DioException error, String key) {
    final data = error.response?.data;
    final detail = data is Map ? data['detail'] : null;
    if (error.response?.statusCode == 409 && detail is Map) {
      // The server has decided; a new attempt is a new action with a new key.
      ref.invalidate(orderTrackingProvider(orderId));
      return CancelState(error: _conflictMessage(detail));
    }
    // A network failure or a busy server: pressing Cancel again repeats the
    // same request safely.
    return CancelState(error: describeApiError(error), key: key);
  }

  String _conflictMessage(Map<dynamic, dynamic> detail) {
    final message = detail['message'];
    final refund = detail['refund_paise'];
    return switch (message) {
      'the cancellation cut-off has passed' =>
        'It is too close to your pickup time to cancel.',
      'the order has changed' when refund is int =>
        'The order changed while you were looking at it. Cancelling now '
            'refunds ${formatPaise(refund)}; check and confirm again.',
      'the order has changed' =>
        'The order changed while you were looking at it. Check and confirm '
            'again.',
      _ when detail['status'] == 'CANCELLED' =>
        'This order is already cancelled.',
      _ => 'This order can no longer be cancelled.',
    };
  }
}

/// FR-37: a cancel button for an order that can still be cancelled, with a
/// confirmation that says what will be refunded.
class CancelOrderSection extends ConsumerWidget {
  const CancelOrderSection(this.orderId, {super.key});

  final String orderId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final order = ref.watch(orderTrackingProvider(orderId)).value?.order;
    final cancel = ref.watch(cancelOrderProvider(orderId));
    final theme = Theme.of(context);
    final refund = cancel.refund;
    if (refund != null) {
      final pending = refund.status == PaymentStatus.pending;
      return Semantics(
        liveRegion: true,
        child: Text(
          pending
              ? 'Order cancelled. A refund of ${formatPaise(refund.amountPaise)} '
                    'is on its way.'
              : 'Order cancelled. ${formatPaise(refund.amountPaise)} refunded.',
          key: const Key('cancel-result'),
        ),
      );
    }
    final error = cancel.error;
    final canCancel = order != null && _cancellable.contains(order.status);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (error != null)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Semantics(
              liveRegion: true,
              child: Text(
                error,
                key: const Key('cancel-error'),
                style: TextStyle(color: theme.colorScheme.error),
              ),
            ),
          ),
        if (canCancel)
          OutlinedButton(
            key: const Key('cancel-order'),
            onPressed: cancel.busy ? null : () => _confirm(context, ref, order),
            child: Text(cancel.busy ? 'Cancelling…' : 'Cancel order'),
          ),
      ],
    );
  }

  Future<void> _confirm(
    BuildContext context,
    WidgetRef ref,
    OrderDetailOut order,
  ) async {
    final consequence = order.status == OrderStatus.accepted
        ? 'You will get a full refund of ${formatPaise(order.paidPaise)}, '
              'and your pickup seat is released.'
        : 'The kitchen has already started preparing it, so only part of '
              'what you paid is refunded. Your pickup seat is released.';
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Cancel this order?'),
        content: Text(consequence),
        actions: [
          TextButton(
            key: const Key('keep-order'),
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Keep order'),
          ),
          FilledButton(
            key: const Key('confirm-cancel'),
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Cancel order'),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      await ref
          .read(cancelOrderProvider(orderId).notifier)
          .cancel(order.version);
    }
  }
}
