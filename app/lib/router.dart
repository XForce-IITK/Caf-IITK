import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'api/api.dart';
import 'auth/login_screen.dart';
import 'auth/register_screen.dart';
import 'auth/session.dart';
import 'dashboards/dashboards.dart';
import 'student/student_dashboard.dart';

const loginPath = '/login';
const registerPath = '/register';

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

final routerProvider = Provider<GoRouter>((ref) {
  final sessionChanged = ValueNotifier<Session?>(ref.read(sessionProvider));
  ref.listen(sessionProvider, (_, session) => sessionChanged.value = session);
  ref.onDispose(sessionChanged.dispose);

  final router = GoRouter(
    initialLocation: loginPath,
    refreshListenable: sessionChanged,
    redirect: (context, state) =>
        redirectFor(ref.read(sessionProvider), state.matchedLocation),
    routes: [
      GoRoute(path: '/', redirect: (context, state) => loginPath),
      GoRoute(path: loginPath, builder: (_, _) => const LoginScreen()),
      GoRoute(path: registerPath, builder: (_, _) => const RegisterScreen()),
      GoRoute(path: '/student', builder: (_, _) => const StudentDashboard()),
      GoRoute(path: '/kitchen', builder: (_, _) => const KitchenDashboard()),
      GoRoute(path: '/admin', builder: (_, _) => const AdminDashboard()),
    ],
  );
  ref.onDispose(router.dispose);
  return router;
});
