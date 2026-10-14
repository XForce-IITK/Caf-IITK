import 'package:caf_app/api/api.dart';
import 'package:caf_app/auth/session.dart';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_server.dart';

const _user = {
  'id': 'u1',
  'name': 'Asha',
  'email': 'asha@iitk.ac.in',
  'role': 'STUDENT',
};

const _order = {
  'id': 'o1',
  'status': 'ACCEPTED',
  'slot_id': 's1',
  'version': 1,
  'paid_paise': 8000,
  'subsidy_applied': false,
  'created_at': '2026-10-06T06:30:00Z',
  'price': {
    'slot_id': 's1',
    'lines': <Object>[],
    'discounted_subtotal_paise': 8000,
    'subsidy_paise': 0,
    'rounding_adjustment_paise': 0,
    'payable_paise': 8000,
  },
};

Future<void> _logIn(ProviderContainer container) {
  return container
      .read(sessionProvider.notifier)
      .login('asha@iitk.ac.in', 'pw');
}

Future<OrderOut> _placeOrder(ProviderContainer container, String key) {
  return container
      .read(apiProvider)
      .ordering
      .placeOrder(
        idempotencyKey: key,
        body: const PlaceOrderRequest(
          slotId: 's1',
          lines: [QuoteLineIn(itemId: 'i1', qty: 1)],
          quotedPayablePaise: 8000,
        ),
      );
}

void main() {
  group('request ID', () {
    test('every request carries a fresh X-Request-ID', () async {
      final server = FakeServer((_) => const Reply(200, {'status': 'ok'}));
      final api = containerFor(server).read(apiProvider);

      await api.ops.health();
      await api.ops.health();

      final ids = server.requests
          .map((r) => r.headers['X-Request-ID'])
          .toList();
      expect(ids, everyElement(matches(RegExp(r'^[0-9a-f-]{36}$'))));
      expect(ids.toSet(), hasLength(2));
    });
  });

  group('access token', () {
    test('is attached after login but never sent to login itself', () async {
      final server = FakeServer(
        (r) => r.path == loginUrl
            ? Reply(200, tokens('STUDENT'))
            : const Reply(200, _user),
      );
      final container = containerFor(server);

      await _logIn(container);
      await container.read(apiProvider).identity.me();

      expect(server.to(loginUrl).single.authorization, isNull);
      expect(server.to(meUrl).single.authorization, 'Bearer access-1');
    });

    test('a 401 refreshes the token once and repeats the request', () async {
      final server = FakeServer((r) {
        if (r.path == loginUrl) return Reply(200, tokens('STUDENT'));
        if (r.path == refreshUrl) {
          return Reply(
            200,
            tokens('STUDENT', access: 'access-2', refresh: 'refresh-2'),
          );
        }
        return r.authorization == 'Bearer access-2'
            ? const Reply(200, _user)
            : const Reply(401, {'detail': 'Token expired'});
      });
      final container = containerFor(server);
      await _logIn(container);

      final user = await container.read(apiProvider).identity.me();

      expect(user.name, 'Asha');
      expect(server.to(refreshUrl).single.data, {'refresh_token': 'refresh-1'});
      expect(server.to(refreshUrl).single.authorization, isNull);
      expect(server.to(meUrl).map((r) => r.authorization), [
        'Bearer access-1',
        'Bearer access-2',
      ]);
      expect(container.read(sessionProvider)!.refreshToken, 'refresh-2');
    });

    test('requests that fail together share one refresh', () async {
      final server = FakeServer((r) {
        if (r.path == loginUrl) return Reply(200, tokens('STUDENT'));
        if (r.path == refreshUrl) {
          return Reply(200, tokens('STUDENT', access: 'access-2'));
        }
        return r.authorization == 'Bearer access-2'
            ? const Reply(200, _user)
            : const Reply(401, {'detail': 'Token expired'});
      });
      final container = containerFor(server);
      await _logIn(container);
      final identity = container.read(apiProvider).identity;

      await Future.wait([identity.me(), identity.me(), identity.me()]);

      expect(server.to(refreshUrl), hasLength(1));
    });

    test('a rejected refresh ends the session and reports the 401', () async {
      final server = FakeServer((r) {
        if (r.path == loginUrl) return Reply(200, tokens('STUDENT'));
        return const Reply(401, {'detail': 'Invalid refresh token'});
      });
      final container = containerFor(server);
      await _logIn(container);

      await expectLater(
        container.read(apiProvider).identity.me(),
        throwsA(
          isA<DioException>().having(
            (e) => e.response?.statusCode,
            'status',
            401,
          ),
        ),
      );

      expect(container.read(sessionProvider), isNull);
      expect(server.to(meUrl), hasLength(1));
    });

    test('a second 401 after refreshing is not retried again', () async {
      final server = FakeServer((r) {
        if (r.path == loginUrl) return Reply(200, tokens('STUDENT'));
        if (r.path == refreshUrl) {
          return Reply(200, tokens('STUDENT', access: 'access-2'));
        }
        return const Reply(401, {'detail': 'Not allowed'});
      });
      final container = containerFor(server);
      await _logIn(container);

      await expectLater(
        container.read(apiProvider).identity.me(),
        throwsA(isA<DioException>()),
      );

      expect(server.to(meUrl), hasLength(2));
      expect(server.to(refreshUrl), hasLength(1));
    });

    test(
      'a wrong password is reported, not treated as an expired token',
      () async {
        final server = FakeServer(
          (_) => const Reply(401, {'detail': 'Invalid email or password'}),
        );
        final container = containerFor(server);

        await expectLater(_logIn(container), throwsA(isA<DioException>()));

        expect(server.requests, hasLength(1));
      },
    );
  });

  group('retry with the same idempotency key (NFR-18)', () {
    test('a briefly unavailable server is retried with back-off', () async {
      var calls = 0;
      final server = FakeServer((r) {
        calls++;
        return calls < 3
            ? const Reply(503, {'detail': 'Busy, try again'})
            : const Reply(201, _order);
      });
      final delays = <Duration>[];
      final container = containerFor(server, delays: delays);

      final order = await _placeOrder(container, 'key-1');

      expect(order.id, 'o1');
      expect(server.requests, hasLength(3));
      expect(server.requests.map((r) => r.headers['Idempotency-Key']).toSet(), {
        'key-1',
      });
      expect(delays, const [Duration(milliseconds: 500), Duration(seconds: 1)]);
    });

    test('a network failure is retried too', () async {
      var calls = 0;
      final server = FakeServer((r) {
        calls++;
        if (calls == 1) throw networkFailure(r);
        return const Reply(201, _order);
      });
      final container = containerFor(server, delays: []);

      await _placeOrder(container, 'key-1');

      expect(server.requests, hasLength(2));
    });

    test('it gives up after three retries', () async {
      final server = FakeServer((_) => const Reply(503, {'detail': 'Busy'}));
      final delays = <Duration>[];
      final container = containerFor(server, delays: delays);

      await expectLater(
        _placeOrder(container, 'key-1'),
        throwsA(
          isA<DioException>().having(
            (e) => e.response?.statusCode,
            'status',
            503,
          ),
        ),
      );

      expect(server.requests, hasLength(4));
      expect(delays, const [
        Duration(milliseconds: 500),
        Duration(seconds: 1),
        Duration(seconds: 2),
      ]);
    });

    test('a longer Retry-After from the server is honoured', () async {
      var calls = 0;
      final server = FakeServer((r) {
        calls++;
        return calls == 1
            ? const Reply(503, {'detail': 'Busy'}, {'Retry-After': '3'})
            : const Reply(201, _order);
      });
      final delays = <Duration>[];
      final container = containerFor(server, delays: delays);

      await _placeOrder(container, 'key-1');

      expect(delays, const [Duration(seconds: 3)]);
    });

    test('a sold-out answer is final and is not retried', () async {
      final server = FakeServer(
        (_) => const Reply(409, {'detail': 'Thali is sold out'}),
      );
      final container = containerFor(server, delays: []);

      await expectLater(
        _placeOrder(container, 'key-1'),
        throwsA(isA<DioException>()),
      );

      expect(server.requests, hasLength(1));
    });

    test('a request without an idempotency key is never retried', () async {
      final server = FakeServer((_) => const Reply(503, {'detail': 'Busy'}));
      final container = containerFor(server, delays: []);

      await expectLater(
        container.read(apiProvider).ops.health(),
        throwsA(isA<DioException>()),
      );

      expect(server.requests, hasLength(1));
    });
  });

  test('idempotency keys are unique and accepted by the backend format', () {
    final keys = {for (var i = 0; i < 50; i++) newIdempotencyKey()};

    expect(keys, hasLength(50));
    expect(keys, everyElement(matches(RegExp(r'^[A-Za-z0-9._:-]{1,100}$'))));
    expect(
      keys,
      everyElement(
        matches(
          RegExp(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-'),
        ),
      ),
    );
  });
}
