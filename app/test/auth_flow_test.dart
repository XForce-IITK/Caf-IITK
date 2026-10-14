import 'package:caf_app/api/api.dart';
import 'package:caf_app/auth/session.dart';
import 'package:caf_app/main.dart';
import 'package:caf_app/router.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_server.dart';

Future<ProviderContainer> _start(WidgetTester tester, FakeServer server) async {
  final container = containerFor(server);
  await tester.pumpWidget(
    UncontrolledProviderScope(container: container, child: const CafApp()),
  );
  await tester.pumpAndSettle();
  return container;
}

Future<void> _logIn(WidgetTester tester) async {
  await tester.enterText(find.byKey(const Key('email')), 'asha@iitk.ac.in');
  await tester.enterText(find.byKey(const Key('password')), 'correct-horse');
  await tester.tap(find.byKey(const Key('submit')));
  await tester.pumpAndSettle();
}

FakeServer _serverFor(String role) {
  return FakeServer(
    (r) => r.path == loginUrl ? Reply(200, tokens(role)) : const Reply(204),
  );
}

String _location(ProviderContainer container) {
  return container
      .read(routerProvider)
      .routerDelegate
      .currentConfiguration
      .uri
      .path;
}

void main() {
  testWidgets('the app opens on the login screen', (tester) async {
    final container = await _start(tester, _serverFor('STUDENT'));

    expect(find.text('Log in'), findsWidgets);
    expect(_location(container), '/login');
  });

  for (final (role, path, title) in [
    ('STUDENT', '/student', 'Student'),
    ('KITCHEN', '/kitchen', 'Kitchen'),
    ('ADMIN', '/admin', 'Administrator'),
  ]) {
    testWidgets('TC-US02-AC1: a $role logs in and sees only the $title '
        'dashboard', (tester) async {
      final server = _serverFor(role);
      final container = await _start(tester, server);

      await _logIn(tester);

      expect(_location(container), path);
      expect(find.widgetWithText(AppBar, title), findsOneWidget);
      expect(server.to(loginUrl).single.data, {
        'email': 'asha@iitk.ac.in',
        'password': 'correct-horse',
      });

      // Every other role's dashboard, and the login screen, bounce back.
      for (final other in ['/student', '/kitchen', '/admin', '/login', '/x']) {
        container.read(routerProvider).go(other);
        await tester.pumpAndSettle();
        expect(_location(container), path, reason: 'from $other');
      }
    });
  }

  testWidgets('a logged-out user cannot open a dashboard', (tester) async {
    final container = await _start(tester, _serverFor('STUDENT'));

    for (final path in ['/student', '/kitchen', '/admin', '/']) {
      container.read(routerProvider).go(path);
      await tester.pumpAndSettle();
      expect(_location(container), '/login', reason: 'from $path');
    }
  });

  testWidgets('TC-US02-AC2: a wrong password shows the server\'s generic '
      'message', (tester) async {
    final server = FakeServer(
      (_) => const Reply(401, {'detail': 'Invalid email or password'}),
    );
    final container = await _start(tester, server);

    await _logIn(tester);

    expect(find.text('Invalid email or password'), findsOneWidget);
    expect(_location(container), '/login');
    expect(container.read(sessionProvider), isNull);
  });

  testWidgets('an unreachable server is explained', (tester) async {
    final server = FakeServer((r) => throw networkFailure(r));
    await _start(tester, server);

    await _logIn(tester);

    expect(find.textContaining('Could not reach the server'), findsOneWidget);
  });

  testWidgets('empty login fields are caught before any request', (
    tester,
  ) async {
    final server = _serverFor('STUDENT');
    await _start(tester, server);

    await tester.tap(find.byKey(const Key('submit')));
    await tester.pumpAndSettle();

    expect(find.text('Enter your email'), findsOneWidget);
    expect(find.text('Enter your password'), findsOneWidget);
    expect(server.requests, isEmpty);
  });

  testWidgets('logging out revokes the refresh token and returns to login', (
    tester,
  ) async {
    final server = _serverFor('STUDENT');
    final container = await _start(tester, server);
    await _logIn(tester);

    await tester.tap(find.byKey(const Key('logout')));
    await tester.pumpAndSettle();

    expect(server.to(logoutUrl).single.data, {'refresh_token': 'refresh-1'});
    expect(server.to(logoutUrl).single.authorization, 'Bearer access-1');
    expect(_location(container), '/login');
    expect(container.read(sessionProvider), isNull);
  });

  testWidgets('logging out works even when the server cannot be reached', (
    tester,
  ) async {
    final server = FakeServer(
      (r) => r.path == loginUrl
          ? Reply(200, tokens('KITCHEN'))
          : throw networkFailure(r),
    );
    final container = await _start(tester, server);
    await _logIn(tester);

    await tester.tap(find.byKey(const Key('logout')));
    await tester.pumpAndSettle();

    expect(_location(container), '/login');
  });

  testWidgets('a session that expires sends the user back to login', (
    tester,
  ) async {
    final server = FakeServer((r) {
      if (r.path == loginUrl) return Reply(200, tokens('STUDENT'));
      return const Reply(401, {'detail': 'Invalid refresh token'});
    });
    final container = await _start(tester, server);
    await _logIn(tester);
    expect(_location(container), '/student');

    await tester.runAsync(() async {
      try {
        await container.read(apiProvider).identity.me();
      } on Object {
        // The 401 is expected; the redirect is what matters here.
      }
    });
    await tester.pumpAndSettle();

    expect(_location(container), '/login');
  });

  testWidgets('a role this client does not know is not let in', (tester) async {
    final container = await _start(tester, _serverFor('AUDITOR'));

    await _logIn(tester);

    expect(_location(container), '/login');
  });

  group('registration', () {
    Future<void> open(WidgetTester tester) async {
      await tester.tap(find.text('New student? Create an account'));
      await tester.pumpAndSettle();
    }

    Future<void> fill(
      WidgetTester tester, {
      String name = 'Asha',
      String email = 'asha@iitk.ac.in',
      String password = 'correct-horse',
    }) async {
      await tester.enterText(find.byKey(const Key('name')), name);
      await tester.enterText(find.byKey(const Key('email')), email);
      await tester.enterText(find.byKey(const Key('password')), password);
      await tester.tap(find.byKey(const Key('submit')));
      await tester.pumpAndSettle();
    }

    testWidgets('a new student registers and lands on the Student dashboard', (
      tester,
    ) async {
      final server = FakeServer((r) {
        if (r.path == registerUrl) {
          return const Reply(201, {
            'id': 'u1',
            'name': 'Asha',
            'email': 'asha@iitk.ac.in',
            'role': 'STUDENT',
          });
        }
        return Reply(200, tokens('STUDENT'));
      });
      final container = await _start(tester, server);
      await open(tester);

      await fill(tester);

      expect(server.to(registerUrl).single.data, {
        'name': 'Asha',
        'email': 'asha@iitk.ac.in',
        'password': 'correct-horse',
      });
      expect(server.to(loginUrl), hasLength(1));
      expect(_location(container), '/student');
    });

    testWidgets('an address outside IITK and a short password are refused '
        'before any request', (tester) async {
      final server = _serverFor('STUDENT');
      await _start(tester, server);
      await open(tester);

      await fill(tester, name: ' ', email: 'asha@gmail.com', password: 'short');

      expect(find.text('Enter your name'), findsOneWidget);
      expect(find.text('Use your @iitk.ac.in address'), findsOneWidget);
      expect(find.text('Use at least 8 characters'), findsOneWidget);
      expect(server.requests, isEmpty);
    });

    testWidgets('an address without @ is refused', (tester) async {
      await _start(tester, _serverFor('STUDENT'));
      await open(tester);

      await fill(tester, email: 'asha');

      expect(find.text('Enter a valid email address'), findsOneWidget);
    });

    testWidgets('an email that is already registered is reported', (
      tester,
    ) async {
      final server = FakeServer(
        (_) => const Reply(409, {'detail': 'Email already registered'}),
      );
      final container = await _start(tester, server);
      await open(tester);

      await fill(tester);

      expect(find.text('Email already registered'), findsOneWidget);
      expect(_location(container), '/register');
    });

    testWidgets('the link back returns to login', (tester) async {
      final container = await _start(tester, _serverFor('STUDENT'));
      await open(tester);

      await tester.tap(find.text('Already registered? Log in'));
      await tester.pumpAndSettle();

      expect(_location(container), '/login');
    });
  });

  for (final width in [360.0, 1920.0]) {
    testWidgets('NFR-33: login and register fit a ${width.toInt()} px wide '
        'window', (tester) async {
      tester.view.physicalSize = Size(width, 640);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);

      await _start(tester, _serverFor('STUDENT'));
      expect(tester.takeException(), isNull);
      final field = tester.getSize(find.byKey(const Key('email')));
      expect(field.width, lessThanOrEqualTo(420));
      expect(field.width, lessThanOrEqualTo(width - 48));

      await tester.tap(find.text('New student? Create an account'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });
  }
}
