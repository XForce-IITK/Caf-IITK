import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api.dart';

/// A logged-in user's tokens and role.
class Session {
  const Session({
    required this.accessToken,
    required this.refreshToken,
    required this.role,
  });

  Session.fromTokens(TokenPair tokens)
    : accessToken = tokens.accessToken,
      refreshToken = tokens.refreshToken,
      role = tokens.role;

  final String accessToken;
  final String refreshToken;
  final Role role;
}

/// The current session, or null when logged out. Tokens are kept in memory
/// only, so reloading the page logs the user out.
final sessionProvider = NotifierProvider<SessionController, Session?>(
  SessionController.new,
);

class SessionController extends Notifier<Session?> {
  Future<bool>? _refreshing;

  @override
  Session? build() => null;

  IdentityClient get _identity => ref.read(apiProvider).identity;

  Future<void> login(String email, String password) async {
    final tokens = await _identity.login(
      body: LoginRequest(email: email, password: password),
    );
    state = Session.fromTokens(tokens);
  }

  /// Registers a Student account (FR-1) and logs straight in.
  Future<void> register(String name, String email, String password) async {
    await _identity.register(
      body: RegisterRequest(name: name, email: email, password: password),
    );
    await login(email, password);
  }

  /// Revokes the refresh token on the server; the local session ends even if
  /// that call fails.
  Future<void> logout() async {
    final session = state;
    if (session == null) return;
    try {
      await _identity.logout(
        body: RefreshRequest(refreshToken: session.refreshToken),
      );
    } on Object {
      // The session is dropped locally regardless.
    }
    state = null;
  }

  /// Rotates the tokens. Concurrent callers share one request, because a
  /// refresh token can be used only once. Returns false and logs out if the
  /// refresh token is no longer valid.
  Future<bool> refresh() {
    return _refreshing ??= _refresh().whenComplete(() => _refreshing = null);
  }

  Future<bool> _refresh() async {
    final session = state;
    if (session == null) return false;
    try {
      final tokens = await _identity.refresh(
        body: RefreshRequest(refreshToken: session.refreshToken),
      );
      state = Session.fromTokens(tokens);
      return true;
    } on Object {
      state = null;
      return false;
    }
  }
}
