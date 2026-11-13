import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api.dart';
import 'token_store.dart';

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

  /// Null on the web, where the refresh token is an HttpOnly cookie.
  final String? refreshToken;
  final Role role;
}

/// The current session, or null when logged out (CAFIITK-207). The access
/// token stays in memory only; the refresh token is kept by
/// [RefreshTokenStore] (an HttpOnly cookie on the web, secure storage on
/// Android), so a reload restores the session through [sessionRestoreProvider].
final sessionProvider = NotifierProvider<SessionController, Session?>(
  SessionController.new,
);

/// Restores the session once when the app starts. While it is loading, the
/// router shows the loading screen instead of sending the user to login.
final sessionRestoreProvider = FutureProvider<void>(
  (ref) => ref.read(sessionProvider.notifier).restore(),
);

class SessionController extends Notifier<Session?> {
  Future<bool>? _refreshing;

  @override
  Session? build() => null;

  IdentityClient get _identity => ref.read(apiProvider).identity;

  RefreshTokenStore get _store => ref.read(refreshTokenStoreProvider);

  Future<void> login(String email, String password) async {
    final tokens = await _identity.login(
      body: LoginRequest(email: email, password: password),
    );
    await _keep(tokens);
  }

  /// Registers a Student account (FR-1) and logs straight in.
  Future<void> register(String name, String email, String password) async {
    await _identity.register(
      body: RegisterRequest(name: name, email: email, password: password),
    );
    await login(email, password);
  }

  /// Exchanges the kept refresh token for a new session. Never throws: any
  /// failure leaves the user logged out.
  /// A session that already exists (a login that finished first) is kept.
  Future<void> restore() async {
    if (state != null) return;
    try {
      final saved = await _store.read();
      if (saved == null && !_store.usesCookie) return;
      final tokens = await _identity.refresh(
        body: RefreshRequest(refreshToken: saved),
      );
      if (state == null) await _keep(tokens);
    } on Object {
      if (state == null) await _forget();
    }
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
    await _forget();
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
      await _keep(tokens);
      return true;
    } on Object {
      await _forget();
      return false;
    }
  }

  Future<void> _keep(TokenPair tokens) async {
    state = Session.fromTokens(tokens);
    final refreshToken = tokens.refreshToken;
    if (refreshToken == null) return;
    try {
      await _store.write(refreshToken);
    } on Object {
      // Storage failing only means the next start asks for a login.
    }
  }

  Future<void> _forget() async {
    state = null;
    try {
      await _store.clear();
    } on Object {
      // Nothing more can be done; the token is unusable once rotated or revoked.
    }
  }
}
