import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'api/api.dart';
import 'auth/login_screen.dart';
import 'auth/register_screen.dart';
import 'auth/session.dart';
import 'dashboards/dashboards.dart';
import 'student/order_history.dart';
import 'student/student_dashboard.dart';

const loginPath = '/login';
const registerPath = '/register';

/// Shown while the session is restored at start-up (CAFIITK-207).
const loadingPath = '/loading';

/// The one dashboard a role may open (FR-5). Null for a role this client does
/// not know, which is treated as logged out.
String? dashboardPath(Role role) {
  return switch (role) {
    Role.student => '/student',
    Role.kitchen => '/kitchen',
    Role.admin => '/admin',
    Role.$unknown => null,
  };
}

/// Where to send the user instead of [location], or null to stay. Logged-out
/// users see only login and register; a logged-in user sees only their own
/// role's dashboard. The server still enforces every permission; this guard
/// is for usability.
String? redirectFor(Session? session, String location) {
  final home = session == null ? null : dashboardPath(session.role);
  if (home == null) {
    return location == loginPath || location == registerPath ? null : loginPath;
  }
  final inOwnDashboard = location == home || location.startsWith('$home/');
  return inOwnDashboard ? null : home;
}

/// [redirectFor], plus start-up (CAFIITK-207): while the session is being
/// restored every page waits on [loadingPath], which remembers where the user
/// was; once restored, the user goes back there if their role may see it.
String? startupRedirect({
  required bool restoring,
  required Session? session,
  required Uri uri,
}) {
  if (restoring) {
    if (uri.path == loadingPath) return null;
    return Uri(
      path: loadingPath,
      queryParameters: {'from': uri.toString()},
    ).toString();
  }
  if (uri.path != loadingPath) return redirectFor(session, uri.path);
  final from = Uri.tryParse(uri.queryParameters['from'] ?? '');
  // Only a path inside this app, never another site or the loading page.
  final target =
      from == null ||
          from.hasScheme ||
          from.hasAuthority ||
          !from.path.startsWith('/') ||
          from.path == loadingPath
      ? Uri(path: loginPath)
      : from;
  return redirectFor(session, target.path) ?? target.toString();
}

final routerProvider = Provider<GoRouter>((ref) {
  final changed = ValueNotifier<int>(0);
  void notify() => changed.value++;
  ref.listen(sessionProvider, (_, _) => notify());
  ref.listen(sessionRestoreProvider, (_, _) => notify());
  ref.onDispose(changed.dispose);

  final router = GoRouter(
    initialLocation: loginPath,
    refreshListenable: changed,
    redirect: (context, state) => startupRedirect(
      restoring: ref.read(sessionRestoreProvider).isLoading,
      session: ref.read(sessionProvider),
      uri: state.uri,
    ),
    routes: [
      GoRoute(path: '/', redirect: (context, state) => loginPath),
      GoRoute(
        path: loadingPath,
        builder: (_, _) =>
            const Scaffold(body: Center(child: CircularProgressIndicator())),
      ),
      GoRoute(path: loginPath, builder: (_, _) => const LoginScreen()),
      GoRoute(path: registerPath, builder: (_, _) => const RegisterScreen()),
      GoRoute(
        path: '/student',
        builder: (_, _) => const StudentDashboard(),
        routes: [
          GoRoute(
            path: 'orders',
            builder: (_, _) => const MyOrdersScreen(),
            routes: [
              GoRoute(
                path: ':orderId',
                builder: (_, state) =>
                    OrderHistoryScreen(state.pathParameters['orderId']!),
              ),
            ],
          ),
        ],
      ),
      GoRoute(path: '/kitchen', builder: (_, _) => const KitchenDashboard()),
      GoRoute(path: '/admin', builder: (_, _) => const AdminDashboard()),
    ],
  );
  ref.onDispose(router.dispose);
  return router;
});
