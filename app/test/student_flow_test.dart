import 'package:caf_app/auth/session.dart';
import 'package:caf_app/main.dart';
import 'package:caf_app/student/format.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_server.dart';

Map<String, Object?> _item(
  String id,
  String name,
  int pricePaise, {
  int left = 10,
  String? reason,
}) {
  return {
    'id': id,
    'name': name,
    'description': 'Fresh $name',
    'category': 'MEAL',
    'price_paise': pricePaise,
    'available_portions': left,
    'orderable': reason == null,
    'not_orderable_reason': reason,
  };
}

Map<String, Object?> _slot(
  String id,
  String startUtc,
  String endUtc, {
  int seats = 7,
  String? reason,
}) {
  return {
    'id': id,
    'starts_at': startUtc,
    'ends_at': endUtc,
    'remaining_seats': seats,
    'bookable': reason == null,
    'not_bookable_reason': reason,
  };
}

Map<String, Object?> _quote({int payable = 14000}) {
  return {
    'slot_id': 's1',
    'lines': [
      {
        'item_id': 'thali',
        'name': 'Thali',
        'unit_price_paise': 8000,
        'qty': 2,
        'line_base_paise': 16000,
        'rule_id': 'r1',
        'discount_pct': 10,
        'line_discount_paise': 1600,
        'line_total_paise': 14400,
      },
    ],
    'discounted_subtotal_paise': 14400,
    'subsidy_paise': 430,
    'rounding_adjustment_paise': 30,
    'payable_paise': payable,
  };
}

Map<String, Object?> _order(String status) {
  return {
    'id': 'o1',
    'status': status,
    'slot_id': 's1',
    'version': 1,
    'paid_paise': status == 'ACCEPTED' ? 14000 : 0,
    'subsidy_applied': true,
    'price': _quote(),
    'created_at': '2026-10-06T05:00:00Z',
  };
}

Map<String, Object?> _step(String? from, String to, String at, [String? role]) {
  return {
    'from_status': from,
    'to_status': to,
    'at': at,
    'actor_role': role,
    'reason': null,
  };
}

/// The order as GET /orders/{id} returns it, with history up to [status].
Map<String, Object?> _tracked(String status) {
  final steps = [
    _step(null, 'PENDING_PAYMENT', '2026-10-06T05:00:00Z', 'STUDENT'),
    _step('PENDING_PAYMENT', 'ACCEPTED', '2026-10-06T05:00:01Z'),
    _step('ACCEPTED', 'PREPARING', '2026-10-06T06:31:00Z', 'KITCHEN'),
    _step('PREPARING', 'READY', '2026-10-06T06:40:00Z', 'KITCHEN'),
    _step('READY', 'PICKED_UP', '2026-10-06T06:50:00Z', 'KITCHEN'),
  ];
  if (status == 'CANCELLED') {
    return {
      ..._order(status),
      'version': 3,
      'history': [
        ...steps.sublist(0, 2),
        _step('ACCEPTED', 'CANCELLED', '2026-10-06T05:30:00Z', 'STUDENT'),
      ],
    };
  }
  final reached = steps.indexWhere((step) => step['to_status'] == status);
  return {
    ..._order(status),
    'version': reached,
    'history': steps.sublist(0, reached + 1),
  };
}

/// caf-api as the Student flow sees it. Tests replace [placeOrder] and the
/// other handlers to script a scenario.
class _Cafe {
  List<Map<String, Object?>> items = [
    _item('thali', 'Thali', 8000, left: 2),
    _item('lassi', 'Lassi', 3000, left: 0, reason: 'SOLD_OUT'),
    _item('samosa', 'Samosa', 1500, left: 5, reason: 'UNAVAILABLE'),
  ];
  List<Map<String, Object?>> slots = [
    // 12:15 - 12:30 IST
    _slot('s1', '2026-10-06T06:45:00Z', '2026-10-06T07:00:00Z'),
    _slot('s2', '2026-10-06T07:00:00Z', '2026-10-06T07:15:00Z', seats: 1),
    _slot('s3', '2026-10-06T07:15:00Z', '2026-10-06T07:30:00Z', reason: 'FULL'),
    _slot(
      's4',
      '2026-10-06T06:30:00Z',
      '2026-10-06T06:45:00Z',
      reason: 'CLOSED',
    ),
  ];
  Reply Function(Seen request) menu = (_) => const Reply(500);
  Reply Function(Seen request) quote = (_) => Reply(200, _quote());
  Reply Function(Seen request) placeOrder = (_) =>
      Reply(201, _order('ACCEPTED'));
  Reply Function(Seen request) tracking = (_) =>
      Reply(200, _tracked('ACCEPTED'));
  Reply Function(Seen request) cancel = (_) => Reply(200, {
    ..._order('CANCELLED'),
    'version': 3,
    'refund': {'amount_paise': 14000, 'status': 'SUCCEEDED'},
  });
  final delays = <Duration>[];

  _Cafe() {
    menu = (_) => Reply(200, {'service_date': '2026-10-06', 'items': items});
  }

  late final server = FakeServer(
    (r) => switch (r.path) {
      loginUrl => Reply(200, tokens('STUDENT')),
      menuUrl => menu(r),
      slotsUrl => Reply(200, {'service_date': '2026-10-06', 'slots': slots}),
      quotesUrl => quote(r),
      ordersUrl => placeOrder(r),
      '$ordersUrl/o1' => tracking(r),
      '$ordersUrl/o1/cancel' => cancel(r),
      _ => const Reply(204),
    },
  );

  Future<void> open(
    WidgetTester tester, {
    Size size = const Size(800, 2400),
  }) async {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final container = containerFor(server, delays: delays);
    await tester.runAsync(
      () =>
          container.read(sessionProvider.notifier).login('a@iitk.ac.in', 'pw'),
    );
    await tester.pumpWidget(
      UncontrolledProviderScope(container: container, child: const CafApp()),
    );
    await tester.pumpAndSettle();
  }
}

Future<void> _tap(WidgetTester tester, String key) async {
  final finder = find.byKey(Key(key));
  await tester.ensureVisible(finder);
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

/// Two Thalis in the 12:15 slot, priced.
Future<void> _reviewTwoThalis(WidgetTester tester) async {
  await _tap(tester, 'add-thali');
  await _tap(tester, 'add-thali');
  await _tap(tester, 'slot-s1');
  await _tap(tester, 'review');
}

bool _enabled(WidgetTester tester, String key) {
  final widget = tester.widget(find.byKey(Key(key)));
  return switch (widget) {
    IconButton(:final onPressed) => onPressed != null,
    ButtonStyleButton(:final onPressed) => onPressed != null,
    ChoiceChip(:final onSelected) => onSelected != null,
    _ => throw StateError('not a button: $widget'),
  };
}

String _errorText(WidgetTester tester) {
  return tester.widget<Text>(find.byKey(const Key('checkout-error'))).data!;
}

void main() {
  test('money and times are formatted for the cafeteria', () {
    expect(formatPaise(8000), '₹80');
    expect(formatPaise(8050), '₹80.50');
    expect(formatPaise(5), '₹0.05');
    expect(formatPaise(-1600), '−₹16');
    expect(formatIstTime(DateTime.utc(2026, 10, 6, 6, 45)), '12:15');
    expect(formatIstTime(DateTime.utc(2026, 10, 6, 18, 35)), '00:05');
  });

  testWidgets('the menu shows price, portions left and why an item cannot be '
      'ordered', (tester) async {
    final cafe = _Cafe();
    await cafe.open(tester);

    expect(find.text('Thali'), findsOneWidget);
    expect(find.text('₹80'), findsOneWidget);
    expect(find.text('2 left'), findsOneWidget);
    expect(find.text('Sold out'), findsOneWidget);
    expect(find.text('Unavailable'), findsOneWidget);
    expect(_enabled(tester, 'add-thali'), isTrue);
    expect(_enabled(tester, 'add-lassi'), isFalse);
    expect(_enabled(tester, 'add-samosa'), isFalse);
  });

  testWidgets('slots show remaining seats and only bookable ones can be '
      'chosen', (tester) async {
    final cafe = _Cafe();
    await cafe.open(tester);

    expect(find.text('12:15 – 12:30 · 7 seats left'), findsOneWidget);
    expect(find.text('12:30 – 12:45 · 1 seat left'), findsOneWidget);
    expect(find.text('12:45 – 13:00 · Full'), findsOneWidget);
    expect(find.text('12:00 – 12:15 · Closed'), findsOneWidget);
    expect(_enabled(tester, 'slot-s1'), isTrue);
    expect(_enabled(tester, 'slot-s3'), isFalse);
    expect(_enabled(tester, 'slot-s4'), isFalse);
  });

  testWidgets('a quantity cannot go below zero or above the portions left', (
    tester,
  ) async {
    final cafe = _Cafe();
    await cafe.open(tester);
    expect(_enabled(tester, 'remove-thali'), isFalse);

    await _tap(tester, 'add-thali');
    await _tap(tester, 'add-thali');

    expect(find.byKey(const Key('quantity-thali')), findsOneWidget);
    expect(
      tester.widget<Text>(find.byKey(const Key('quantity-thali'))).data,
      '2',
    );
    expect(_enabled(tester, 'add-thali'), isFalse);

    await _tap(tester, 'remove-thali');
    await _tap(tester, 'remove-thali');
    expect(
      tester.widget<Text>(find.byKey(const Key('quantity-thali'))).data,
      '0',
    );
  });

  testWidgets('the order can be reviewed only with an item and a slot', (
    tester,
  ) async {
    final cafe = _Cafe();
    await cafe.open(tester);
    expect(_enabled(tester, 'review'), isFalse);
    expect(
      find.text('Add at least one item and choose a pickup slot.'),
      findsOneWidget,
    );

    await _tap(tester, 'add-thali');
    expect(_enabled(tester, 'review'), isFalse);

    await _tap(tester, 'slot-s1');
    expect(_enabled(tester, 'review'), isTrue);
  });

  testWidgets('NFR-32: the full price breakdown and the seats left are shown '
      'before confirming', (tester) async {
    final cafe = _Cafe();
    await cafe.open(tester);

    await _reviewTwoThalis(tester);

    expect(cafe.server.to(quotesUrl).single.data, {
      'slot_id': 's1',
      'lines': [
        {'item_id': 'thali', 'qty': 2},
      ],
    });
    final quote = find.byKey(const Key('quote'));
    Finder inQuote(String text) =>
        find.descendant(of: quote, matching: find.text(text));
    expect(inQuote('2 × Thali'), findsOneWidget);
    expect(inQuote('₹160'), findsOneWidget);
    expect(inQuote('  Discount 10%'), findsOneWidget);
    expect(inQuote('−₹16'), findsOneWidget);
    expect(inQuote('₹144'), findsOneWidget);
    expect(inQuote('−₹4.30'), findsOneWidget);
    expect(inQuote('₹0.30'), findsOneWidget);
    expect(inQuote('₹140'), findsOneWidget);
    expect(inQuote('Pickup 12:15 – 12:30 · 7 seats left'), findsOneWidget);
    expect(find.text('Confirm and pay ₹140'), findsOneWidget);
    expect(cafe.server.to(ordersUrl), isEmpty);
  });

  testWidgets('confirming places the order at the quoted price and shows it', (
    tester,
  ) async {
    final cafe = _Cafe();
    await cafe.open(tester);
    await _reviewTwoThalis(tester);

    await _tap(tester, 'confirm');

    final request = cafe.server.to(ordersUrl).single;
    expect(request.data, {
      'slot_id': 's1',
      'lines': [
        {'item_id': 'thali', 'qty': 2},
      ],
      'quoted_payable_paise': 14000,
    });
    expect(
      request.headers['Idempotency-Key'],
      matches(RegExp(r'^[0-9a-f-]{36}$')),
    );
    expect(find.text('Order confirmed'), findsOneWidget);
    expect(find.text('You paid ₹140.'), findsOneWidget);
    expect(find.text('Pick it up between 12:15 – 12:30.'), findsOneWidget);
    // Availability is fetched again, since the order changed it.
    expect(cafe.server.to(menuUrl), hasLength(2));
    expect(cafe.server.to(slotsUrl), hasLength(2));

    await _tap(tester, 'place-another');
    expect(find.text('Menu'), findsOneWidget);
    expect(
      tester.widget<Text>(find.byKey(const Key('quantity-thali'))).data,
      '0',
    );
  });

  testWidgets('NFR-32: a refused order names exactly the item and slot that '
      'were unavailable', (tester) async {
    final cafe = _Cafe()
      ..placeOrder = (_) => const Reply(409, {
        'detail': {
          'message': 'Items or slot unavailable',
          'item_ids': ['thali'],
          'slot_id': 's1',
        },
      });
    await cafe.open(tester);
    await _reviewTwoThalis(tester);

    await _tap(tester, 'confirm');

    expect(
      _errorText(tester),
      'No longer available: Thali. The 12:15 – 12:30 slot is no longer '
      'available. Nothing was reserved or charged.',
    );
    expect(find.byKey(const Key('quote')), findsNothing);
    expect(find.byKey(const Key('review')), findsOneWidget);
    expect(cafe.server.to(menuUrl), hasLength(2));
    expect(cafe.server.to(ordersUrl), hasLength(1));
  });

  testWidgets('only the slot is named when only the slot filled up', (
    tester,
  ) async {
    final cafe = _Cafe()
      ..placeOrder = (_) => const Reply(409, {
        'detail': {
          'message': 'Items or slot unavailable',
          'item_ids': <String>[],
          'slot_id': 's1',
        },
      });
    await cafe.open(tester);
    await _reviewTwoThalis(tester);

    await _tap(tester, 'confirm');

    expect(
      _errorText(tester),
      'The 12:15 – 12:30 slot is no longer available. Nothing was reserved '
      'or charged.',
    );
  });

  testWidgets('FR-26: a changed price is shown and must be confirmed again', (
    tester,
  ) async {
    var attempts = 0;
    final cafe = _Cafe();
    cafe.placeOrder = (_) {
      attempts++;
      return attempts == 1
          ? Reply(409, {
              'detail': {
                'message': 'Price changed',
                'quote': _quote(payable: 15000),
              },
            })
          : Reply(201, _order('ACCEPTED'));
    };
    await cafe.open(tester);
    await _reviewTwoThalis(tester);

    await _tap(tester, 'confirm');

    expect(_errorText(tester), contains('The price changed'));
    expect(find.text('Confirm and pay ₹150'), findsOneWidget);

    await _tap(tester, 'confirm');

    final [first, second] = cafe.server.to(ordersUrl).toList();
    expect((second.data! as Map)['quoted_payable_paise'], 15000);
    // A different request body needs a different idempotency key.
    expect(
      second.headers['Idempotency-Key'],
      isNot(first.headers['Idempotency-Key']),
    );
    expect(find.text('Order confirmed'), findsOneWidget);
  });

  testWidgets('ordering before the menu opens says when it opens', (
    tester,
  ) async {
    final cafe = _Cafe()
      ..placeOrder = (_) => const Reply(409, {
        'detail': {
          'message': 'Ordering is not open yet',
          'opens_at': '2026-10-06T11:00:00+05:30',
        },
      });
    await cafe.open(tester);
    await _reviewTwoThalis(tester);

    await _tap(tester, 'confirm');

    expect(_errorText(tester), 'Ordering opens at 11:00.');
  });

  testWidgets('a failed payment is explained and the cart is kept', (
    tester,
  ) async {
    final cafe = _Cafe()
      ..placeOrder = (_) => Reply(201, _order('PAYMENT_FAILED'));
    await cafe.open(tester);
    await _reviewTwoThalis(tester);

    await _tap(tester, 'confirm');

    expect(_errorText(tester), contains('payment did not go through'));
    expect(find.text('Order confirmed'), findsNothing);
    expect(
      tester.widget<Text>(find.byKey(const Key('quantity-thali'))).data,
      '2',
    );
    expect(_enabled(tester, 'review'), isTrue);
  });

  testWidgets('NFR-18: a busy server is retried with the same key and the '
      'order goes through', (tester) async {
    var attempts = 0;
    final cafe = _Cafe();
    cafe.placeOrder = (_) {
      attempts++;
      return attempts < 3
          ? const Reply(
              503,
              {'detail': 'Busy, try again'},
              {'Retry-After': '1'},
            )
          : Reply(201, _order('ACCEPTED'));
    };
    await cafe.open(tester);
    await _reviewTwoThalis(tester);

    await _tap(tester, 'confirm');

    final requests = cafe.server.to(ordersUrl).toList();
    expect(requests, hasLength(3));
    expect(
      requests.map((r) => r.headers['Idempotency-Key']).toSet(),
      hasLength(1),
    );
    expect(cafe.delays, const [Duration(seconds: 1), Duration(seconds: 1)]);
    expect(find.text('Order confirmed'), findsOneWidget);
  });

  testWidgets('when retries run out, confirming again reuses the same key', (
    tester,
  ) async {
    final cafe = _Cafe()..placeOrder = (r) => throw networkFailure(r);
    await cafe.open(tester);
    await _reviewTwoThalis(tester);

    await _tap(tester, 'confirm');

    expect(_errorText(tester), contains('Could not reach the server'));
    expect(cafe.server.to(ordersUrl), hasLength(4));
    expect(find.text('Confirm and pay ₹140'), findsOneWidget);

    cafe.placeOrder = (_) => Reply(201, _order('ACCEPTED'));
    await _tap(tester, 'confirm');

    expect(
      cafe.server
          .to(ordersUrl)
          .map((r) => r.headers['Idempotency-Key'])
          .toSet(),
      hasLength(1),
    );
    expect(find.text('Order confirmed'), findsOneWidget);
  });

  testWidgets('changing the cart after a review discards the old price', (
    tester,
  ) async {
    final cafe = _Cafe();
    await cafe.open(tester);
    await _reviewTwoThalis(tester);
    expect(find.byKey(const Key('quote')), findsOneWidget);

    await _tap(tester, 'remove-thali');

    expect(find.byKey(const Key('quote')), findsNothing);
    expect(find.byKey(const Key('confirm')), findsNothing);
    expect(_enabled(tester, 'review'), isTrue);
  });

  testWidgets('a quantity over the limit is reported from the quote', (
    tester,
  ) async {
    final cafe = _Cafe()
      ..quote = (_) =>
          const Reply(422, {'detail': 'quantity per item may not exceed 1'});
    await cafe.open(tester);

    await _reviewTwoThalis(tester);

    expect(_errorText(tester), 'quantity per item may not exceed 1');
    expect(find.byKey(const Key('quote')), findsNothing);
  });

  testWidgets('a menu that fails to load can be retried', (tester) async {
    final cafe = _Cafe();
    final working = cafe.menu;
    cafe.menu = (r) => throw networkFailure(r);
    await cafe.open(tester);
    expect(find.textContaining('Could not reach the server'), findsOneWidget);

    cafe.menu = working;
    await tester.tap(find.text('Try again'));
    await tester.pumpAndSettle();

    expect(find.text('Thali'), findsOneWidget);
  });

  testWidgets('an unconfigured day says so', (tester) async {
    final cafe = _Cafe()
      ..items = []
      ..slots = [];
    await cafe.open(tester);

    expect(
      find.text('No menu has been published for today yet.'),
      findsOneWidget,
    );
    expect(
      find.text('No pickup slots have been set up for today yet.'),
      findsOneWidget,
    );
  });

  group('order tracking (FR-40)', () {
    Future<_Cafe> placed(WidgetTester tester) async {
      final cafe = _Cafe();
      await cafe.open(tester);
      await _reviewTwoThalis(tester);
      await _tap(tester, 'confirm');
      return cafe;
    }

    String status(WidgetTester tester) {
      return tester.widget<Text>(find.byKey(const Key('order-status'))).data!;
    }

    testWidgets('the confirmed order shows its status and history', (
      tester,
    ) async {
      await placed(tester);

      expect(status(tester), 'Confirmed. The kitchen has not started it yet.');
      expect(find.text('10:30'), findsWidgets);
      expect(find.text('Order placed'), findsOneWidget);
      expect(find.text('Payment confirmed'), findsOneWidget);
    });

    testWidgets('TC-US29-AC1: READY set by the kitchen appears within '
        'P-POLL', (tester) async {
      final cafe = await placed(tester);
      final before = cafe.server.to('$ordersUrl/o1').length;

      cafe.tracking = (_) => Reply(200, _tracked('READY'));
      await tester.pump(const Duration(seconds: 9));
      expect(cafe.server.to('$ordersUrl/o1'), hasLength(before));

      await tester.pump(const Duration(seconds: 1));
      await tester.pumpAndSettle();

      expect(status(tester), 'Ready. Collect it during your pickup slot.');
      expect(find.text('Preparation started by the kitchen'), findsOneWidget);
      expect(find.text('Ready for pickup by the kitchen'), findsOneWidget);
      expect(find.text('12:01'), findsOneWidget);
      expect(find.text('12:10'), findsOneWidget);
    });

    testWidgets('polling stops once the order is finished', (tester) async {
      final cafe = await placed(tester);
      cafe.tracking = (_) => Reply(200, _tracked('PICKED_UP'));
      await tester.pump(const Duration(seconds: 10));
      await tester.pumpAndSettle();
      expect(status(tester), 'Picked up. Enjoy your meal.');
      final requests = cafe.server.to('$ordersUrl/o1').length;

      await tester.pump(const Duration(minutes: 1));

      expect(cafe.server.to('$ordersUrl/o1'), hasLength(requests));
    });

    testWidgets('a failed refresh keeps the last status and tries again', (
      tester,
    ) async {
      final cafe = await placed(tester);
      cafe.tracking = (r) => throw networkFailure(r);
      await tester.pump(const Duration(seconds: 10));
      await tester.pumpAndSettle();

      expect(status(tester), 'Confirmed. The kitchen has not started it yet.');
      expect(find.textContaining('Could not refresh'), findsOneWidget);

      cafe.tracking = (_) => Reply(200, _tracked('PREPARING'));
      await tester.pump(const Duration(seconds: 10));
      await tester.pumpAndSettle();

      expect(status(tester), 'Being prepared.');
      expect(find.textContaining('Could not refresh'), findsNothing);
    });

    testWidgets('a status that cannot be loaded can be retried', (
      tester,
    ) async {
      final cafe = _Cafe()..tracking = (_) => const Reply(500);
      await cafe.open(tester);
      await _reviewTwoThalis(tester);
      await _tap(tester, 'confirm');
      expect(
        find.textContaining('Could not load the order status'),
        findsOneWidget,
      );

      cafe.tracking = (_) => Reply(200, _tracked('ACCEPTED'));
      await tester.tap(find.text('Try again'));
      await tester.pumpAndSettle();

      expect(status(tester), 'Confirmed. The kitchen has not started it yet.');
    });

    testWidgets('leaving the order stops polling', (tester) async {
      final cafe = await placed(tester);
      await _tap(tester, 'place-another');
      final requests = cafe.server.to('$ordersUrl/o1').length;

      await tester.pump(const Duration(minutes: 1));

      expect(cafe.server.to('$ordersUrl/o1'), hasLength(requests));
    });
  });

  group('cancelling (FR-37)', () {
    Future<_Cafe> placed(
      WidgetTester tester, {
      String status = 'ACCEPTED',
    }) async {
      final cafe = _Cafe()..tracking = (_) => Reply(200, _tracked(status));
      await cafe.open(tester);
      await _reviewTwoThalis(tester);
      await _tap(tester, 'confirm');
      return cafe;
    }

    String text(WidgetTester tester, String key) {
      return tester.widget<Text>(find.byKey(Key(key))).data!;
    }

    testWidgets('an accepted order is cancelled after confirming, with a full '
        'refund', (tester) async {
      final cafe = await placed(tester);

      await _tap(tester, 'cancel-order');
      expect(find.text('Cancel this order?'), findsOneWidget);
      expect(
        find.text(
          'You will get a full refund of ₹140, and your pickup seat is released.',
        ),
        findsOneWidget,
      );
      cafe.tracking = (_) => Reply(200, _tracked('CANCELLED'));
      await _tap(tester, 'confirm-cancel');

      final request = cafe.server.to('$ordersUrl/o1/cancel').single;
      expect(request.data, {'version': 1});
      expect(
        request.headers['Idempotency-Key'],
        matches(RegExp(r'^[0-9a-f-]{36}$')),
      );
      expect(text(tester, 'cancel-result'), 'Order cancelled. ₹140 refunded.');
      expect(
        tester.widget<Text>(find.byKey(const Key('order-status'))).data,
        'Cancelled.',
      );
      expect(find.byKey(const Key('cancel-order')), findsNothing);
    });

    testWidgets('keeping the order sends nothing', (tester) async {
      final cafe = await placed(tester);

      await _tap(tester, 'cancel-order');
      await _tap(tester, 'keep-order');

      expect(cafe.server.to('$ordersUrl/o1/cancel'), isEmpty);
      expect(find.byKey(const Key('cancel-order')), findsOneWidget);
    });

    testWidgets('a refund still on its way says so', (tester) async {
      final cafe = await placed(tester);
      cafe.cancel = (_) => Reply(200, {
        ..._order('CANCELLED'),
        'refund': {'amount_paise': 14000, 'status': 'PENDING'},
      });

      await _tap(tester, 'cancel-order');
      await _tap(tester, 'confirm-cancel');

      expect(
        text(tester, 'cancel-result'),
        'Order cancelled. A refund of ₹140 is on its way.',
      );
    });

    testWidgets('an order being prepared warns that only part is refunded', (
      tester,
    ) async {
      final cafe = await placed(tester, status: 'PREPARING');

      await _tap(tester, 'cancel-order');
      expect(find.textContaining('only part of what you paid'), findsOneWidget);
      await _tap(tester, 'confirm-cancel');

      expect(cafe.server.to('$ordersUrl/o1/cancel').single.data, {
        'version': 2,
      });
    });

    testWidgets('a ready order cannot be cancelled from the screen', (
      tester,
    ) async {
      await placed(tester, status: 'READY');

      expect(find.byKey(const Key('cancel-order')), findsNothing);
    });

    testWidgets('NFR-5: a changed order shows the new refund and needs a new '
        'confirmation with a new key', (tester) async {
      final cafe = await placed(tester);
      cafe.cancel = (_) => const Reply(409, {
        'detail': {
          'message': 'the order has changed',
          'status': 'PREPARING',
          'version': 2,
          'refund_paise': 7000,
        },
      });
      cafe.tracking = (_) => Reply(200, _tracked('PREPARING'));

      await _tap(tester, 'cancel-order');
      await _tap(tester, 'confirm-cancel');

      expect(
        text(tester, 'cancel-error'),
        'The order changed while you were looking at it. Cancelling now '
        'refunds ₹70; check and confirm again.',
      );
      expect(
        tester.widget<Text>(find.byKey(const Key('order-status'))).data,
        'Being prepared.',
      );

      cafe.cancel = (_) => Reply(200, {
        ..._order('CANCELLED'),
        'refund': {'amount_paise': 7000, 'status': 'SUCCEEDED'},
      });
      await _tap(tester, 'cancel-order');
      await _tap(tester, 'confirm-cancel');

      final [first, second] = cafe.server.to('$ordersUrl/o1/cancel').toList();
      expect(second.data, {'version': 2});
      expect(
        second.headers['Idempotency-Key'],
        isNot(first.headers['Idempotency-Key']),
      );
      expect(text(tester, 'cancel-result'), 'Order cancelled. ₹70 refunded.');
    });

    testWidgets('past the cut-off the reason is explained', (tester) async {
      final cafe = await placed(tester);
      cafe.cancel = (_) => const Reply(409, {
        'detail': {
          'message': 'the cancellation cut-off has passed',
          'status': 'ACCEPTED',
          'version': 1,
          'refund_paise': null,
        },
      });

      await _tap(tester, 'cancel-order');
      await _tap(tester, 'confirm-cancel');

      expect(
        text(tester, 'cancel-error'),
        'It is too close to your pickup time to cancel.',
      );
    });

    testWidgets('an order cancelled elsewhere is reported as such', (
      tester,
    ) async {
      final cafe = await placed(tester);
      cafe.cancel = (_) => const Reply(409, {
        'detail': {
          'message': 'order is CANCELLED',
          'status': 'CANCELLED',
          'version': 3,
          'refund_paise': null,
        },
      });

      await _tap(tester, 'cancel-order');
      await _tap(tester, 'confirm-cancel');

      expect(text(tester, 'cancel-error'), 'This order is already cancelled.');
    });

    testWidgets('any other refusal says it can no longer be cancelled', (
      tester,
    ) async {
      final cafe = await placed(tester);
      cafe.cancel = (_) => const Reply(409, {
        'detail': {
          'message': 'order is READY',
          'status': 'READY',
          'version': 3,
          'refund_paise': null,
        },
      });

      await _tap(tester, 'cancel-order');
      await _tap(tester, 'confirm-cancel');

      expect(
        text(tester, 'cancel-error'),
        'This order can no longer be cancelled.',
      );
    });

    testWidgets('NFR-18: after a network failure, cancelling again reuses the '
        'same key', (tester) async {
      final cafe = await placed(tester);
      cafe.cancel = (r) => throw networkFailure(r);

      await _tap(tester, 'cancel-order');
      await _tap(tester, 'confirm-cancel');

      expect(
        text(tester, 'cancel-error'),
        contains('Could not reach the server'),
      );
      // The interceptor already retried three times with that key.
      expect(cafe.server.to('$ordersUrl/o1/cancel'), hasLength(4));

      cafe.cancel = (_) => Reply(200, {
        ..._order('CANCELLED'),
        'refund': {'amount_paise': 14000, 'status': 'SUCCEEDED'},
      });
      await _tap(tester, 'cancel-order');
      await _tap(tester, 'confirm-cancel');

      expect(
        cafe.server
            .to('$ordersUrl/o1/cancel')
            .map((r) => r.headers['Idempotency-Key'])
            .toSet(),
        hasLength(1),
      );
      expect(text(tester, 'cancel-result'), 'Order cancelled. ₹140 refunded.');
    });
  });

  for (final width in [360.0, 1920.0]) {
    testWidgets('NFR-33: the order flow fits a ${width.toInt()} px wide '
        'window', (tester) async {
      final cafe = _Cafe();
      await cafe.open(tester, size: Size(width, 2400));
      expect(tester.takeException(), isNull);

      await _reviewTwoThalis(tester);
      expect(tester.takeException(), isNull);

      await _tap(tester, 'confirm');
      expect(tester.takeException(), isNull);
      expect(find.text('Order confirmed'), findsOneWidget);
    });
  }
}
