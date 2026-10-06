import 'dart:convert';
import 'dart:typed_data';

import 'package:caf_app/api/api.dart';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

/// Answers every request with [body] and records what was sent.
class _RecordingAdapter implements HttpClientAdapter {
  _RecordingAdapter(this.body, {this.status = 200});

  final Object? body;
  final int status;
  final requests = <RequestOptions>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    return ResponseBody.fromString(
      jsonEncode(body),
      status,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

const _quote = {
  'slot_id': 's1',
  'lines': [
    {
      'item_id': 'i1',
      'name': 'Thali',
      'unit_price_paise': 8000,
      'qty': 2,
      'line_base_paise': 16000,
      'rule_id': null,
      'discount_pct': 0,
      'line_discount_paise': 0,
      'line_total_paise': 16000,
    },
  ],
  'discounted_subtotal_paise': 16000,
  'subsidy_paise': 0,
  'rounding_adjustment_paise': 0,
  'payable_paise': 16000,
};

(ProviderContainer, _RecordingAdapter) _api(Object? body, {int status = 200}) {
  final adapter = _RecordingAdapter(body, status: status);
  final container = ProviderContainer();
  addTearDown(container.dispose);
  container.read(dioProvider).httpClientAdapter = adapter;
  return (container, adapter);
}

void main() {
  test('the client calls caf-api at the configured base URL', () async {
    final (container, adapter) = _api({'status': 'ok'});

    final health = await container.read(apiProvider).ops.health();

    expect(health, {'status': 'ok'});
    expect(adapter.requests.single.uri.toString(), '$apiBaseUrl/health');
  });

  test(
    'placing an order sends the idempotency key and parses the order',
    () async {
      final (container, adapter) = _api({
        'id': 'o1',
        'status': 'ACCEPTED',
        'slot_id': 's1',
        'price': _quote,
        'paid_paise': 16000,
        'subsidy_applied': false,
        'version': 1,
        'created_at': '2026-10-06T06:30:00Z',
      }, status: 201);

      final order = await container
          .read(apiProvider)
          .ordering
          .placeOrder(
            idempotencyKey: 'key-1',
            body: const PlaceOrderRequest(
              slotId: 's1',
              lines: [QuoteLineIn(itemId: 'i1', qty: 2)],
              quotedPayablePaise: 16000,
            ),
          );

      final request = adapter.requests.single;
      expect(request.method, 'POST');
      expect(request.path, '/api/v1/orders');
      expect(request.headers['Idempotency-Key'], 'key-1');
      // Dio encodes the body with jsonEncode, which is what reaches the server.
      expect(jsonDecode(jsonEncode(request.data)), {
        'slot_id': 's1',
        'lines': [
          {'item_id': 'i1', 'qty': 2},
        ],
        'quoted_payable_paise': 16000,
      });
      expect(order.status, OrderStatus.accepted);
      expect(order.price.payablePaise, 16000);
      expect(order.createdAt, DateTime.utc(2026, 10, 6, 6, 30));
    },
  );

  test('a status added on the backend later parses as unknown', () async {
    final (container, _) = _api({
      'id': 'o1',
      'status': 'SOMETHING_NEW',
      'slot_id': 's1',
      'price': _quote,
      'paid_paise': 0,
      'subsidy_applied': false,
      'version': 1,
      'created_at': '2026-10-06T06:30:00Z',
    }, status: 201);

    final order = await container
        .read(apiProvider)
        .ordering
        .placeOrder(
          idempotencyKey: 'key-2',
          body: const PlaceOrderRequest(
            slotId: 's1',
            lines: [QuoteLineIn(itemId: 'i1', qty: 1)],
            quotedPayablePaise: 8000,
          ),
        );

    expect(order.status, OrderStatus.$unknown);
  });

  test('service dates are sent as a date the backend accepts', () async {
    final (container, adapter) = _api({
      'service_date': '2026-10-06',
      'items': <Object>[],
    });

    final menu = await container
        .read(apiProvider)
        .catalogue
        .browseMenu(date: serviceDate(DateTime(2026, 10, 6, 13, 45)));

    expect(
      adapter.requests.single.queryParameters['date'],
      '2026-10-06T00:00:00.000',
    );
    expect(menu.serviceDate, DateTime(2026, 10, 6));
    expect(menu.items, isEmpty);
  });
}
