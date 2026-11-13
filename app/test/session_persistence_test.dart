// CAFIITK-207: a reload or a restart keeps the user logged in, without the
// client ever storing the access token, or (on the web) seeing the refresh token.
import 'package:caf_app/api/api.dart';
import 'package:caf_app/auth/session.dart';
import 'package:caf_app/main.dart';
import 'package:caf_app/router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_server.dart';

const _transport = 'X-Token-Transport';

FakeServer _server({Reply? refresh}) {
  return FakeServer(
    (r) => switch (r.path) {
      loginUrl => Reply(200, tokens('STUDENT')),
      refreshUrl =>
        refresh ??
            Reply(
              200,
              tokens('STUDENT', access: 'access-2', refresh: 'refresh-2'),
            ),
      menuUrl => const Reply(200, {'service_date': '2026-10-06', 'items': []}),
      slotsUrl => const Reply(200, {'service_date': '2026-10-06', 'slots': []}),
      _ => const Reply(204),
    },
  );
}

/// The web server answers cookie-mode auth calls without the refresh token.
Map<String, Object?> _cookieTokens(String access) =>
    tokens('STUDENT', access: access)..['refresh_token'] = null;

Future<ProviderContainer> _start(
  WidgetTester tester,
  FakeServer server,
  MemoryTokenStore store,
) async {
  final container = containerFor(server, store: store);
  await tester.pumpWidget(
    UncontrolledProviderScope(container: container, child: const CafApp()),
  );
  await tester.pumpAndSettle();
  return container;
}

String _location(ProviderContainer container) =>
    container.read(routerProvider).routerDelegate.currentConfiguration.uri.path;

void main() {
  group('Android (refresh token in secure storage)', () {
    testWidgets('a restart with a kept refresh token opens the dashboard', (
      tester,
    ) async {
      final server = _server();
      final store = MemoryTokenStore(token: 'refresh-1');

      final container = await _start(tester, server, store);

      expect(_location(container), '/student');
      expect(server.to(refreshUrl).single.data, {'refresh_token': 'refresh-1'});
      expect(server.to(refreshUrl).single.headers[_transport], isNull);
      // Rotated (NFR-19): the new token replaces the used one.
      expect(store.token, 'refresh-2');
      expect(container.read(sessionProvider)!.accessToken, 'access-2');
    });

    testWidgets('a rejected refresh token is forgotten and login is shown', (
      tester,
    ) async {
      final server = _server(
        refresh: const Reply(401, {'detail': 'Invalid refresh token'}),
      );
      final store = MemoryTokenStore(token: 'revoked');

      final container = await _start(tester, server, store);

      expect(_location(container), '/login');
      expect(store.token, isNull);
      expect(container.read(sessionProvider), isNull);
    });

    testWidgets('with nothing kept, start-up makes no request', (tester) async {
      final server = _server();

      final container = await _start(tester, server, MemoryTokenStore());

      expect(_location(container), '/login');
      expect(server.requests, isEmpty);
    });

    testWidgets('login keeps the refresh token and logout removes it', (
      tester,
    ) async {
      final store = MemoryTokenStore();
      final container = await _start(tester, _server(), store);

      await tester.runAsync(
        () => container
            .read(sessionProvider.notifier)
            .login('asha@iitk.ac.in', 'pw'),
      );
      expect(store.token, 'refresh-1');

      await tester.runAsync(
        () => container.read(sessionProvider.notifier).logout(),
      );
      expect(store.token, isNull);
    });
  });

  group('web (refresh token in an HttpOnly cookie)', () {
    testWidgets('a reload restores the session from the cookie', (
      tester,
    ) async {
      final server = _server(refresh: Reply(200, _cookieTokens('access-2')));
      final store = MemoryTokenStore(usesCookie: true);

      final container = await _start(tester, server, store);

      expect(_location(container), '/student');
      final refresh = server.to(refreshUrl).single;
      expect(refresh.headers[_transport], 'cookie');
      expect(refresh.options.extra['withCredentials'], isTrue);
      expect((refresh.data! as Map)['refresh_token'], isNull);
      expect(container.read(sessionProvider)!.refreshToken, isNull);
      expect(store.token, isNull);
    });

    testWidgets('without a cookie the reload ends on the login screen', (
      tester,
    ) async {
      final server = _server(
        refresh: const Reply(422, {'detail': 'No refresh token presented'}),
      );

      final container = await _start(
        tester,
        server,
        MemoryTokenStore(usesCookie: true),
      );

      expect(_location(container), '/login');
      expect(container.read(sessionProvider), isNull);
    });

    testWidgets('auth calls ask for the cookie; other calls do not', (
      tester,
    ) async {
      final server = FakeServer(
        (r) => switch (r.path) {
          loginUrl => Reply(200, _cookieTokens('access-1')),
          refreshUrl => const Reply(422),
          _ => const Reply(200, {'service_date': '2026-10-06', 'items': []}),
        },
      );
      final container = await _start(
        tester,
        server,
        MemoryTokenStore(usesCookie: true),
      );

      await tester.runAsync(
        () => container
            .read(sessionProvider.notifier)
            .login('asha@iitk.ac.in', 'pw'),
      );
      await tester.pumpAndSettle();

      expect(server.to(loginUrl).single.headers[_transport], 'cookie');
      expect(server.to(menuUrl).first.headers[_transport], isNull);
      expect(server.to(menuUrl).first.options.extra['withCredentials'], isNull);
    });
  });

  group('start-up routing', () {
    final student = Session(
      accessToken: 'a',
      refreshToken: null,
      role: Role.student,
    );

    String? redirect(String location, {bool restoring = false, Session? as}) {
      return startupRedirect(
        restoring: restoring,
        session: as,
        uri: Uri.parse(location),
      );
    }

    test('every page waits on the loading screen while restoring', () {
      expect(
        redirect('/student/orders/abc', restoring: true),
        '/loading?from=%2Fstudent%2Forders%2Fabc',
      );
      expect(redirect('/loading?from=/x', restoring: true), isNull);
    });

    test('after a reload the user returns to the page they were on', () {
      expect(
        redirect('/loading?from=/student/orders/abc', as: student),
        '/student/orders/abc',
      );
    });

    test('a page the role may not see still goes to its dashboard', () {
      expect(redirect('/loading?from=/admin', as: student), '/student');
      expect(redirect('/loading?from=/student/orders/abc'), '/login');
    });

    test('the return address can only be a page of this app', () {
      for (final from in [
        'https://evil.example.org/x',
        '//evil.example.org',
        'student',
        '/loading',
      ]) {
        final encoded = Uri.encodeQueryComponent(from);
        expect(
          redirect('/loading?from=$encoded', as: student),
          '/student',
          reason: from,
        );
        expect(redirect('/loading?from=$encoded'), '/login', reason: from);
      }
    });
  });
}
