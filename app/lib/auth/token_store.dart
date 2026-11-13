import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Where the refresh token is kept between app starts (CAFIITK-207). The
/// access token is never stored: it lives in memory and lasts 15 minutes.
abstract interface class RefreshTokenStore {
  /// True on the web: the server keeps the refresh token in an HttpOnly,
  /// SameSite=Strict cookie that page scripts cannot read, so the client
  /// never holds it and asks for cookie transport instead.
  bool get usesCookie;

  Future<String?> read();

  Future<void> write(String token);

  Future<void> clear();
}

/// Web: the browser holds the token in the cookie; there is nothing to store.
class CookieTokenStore implements RefreshTokenStore {
  const CookieTokenStore();

  @override
  bool get usesCookie => true;

  @override
  Future<String?> read() async => null;

  @override
  Future<void> write(String token) async {}

  @override
  Future<void> clear() async {}
}

/// Android: the platform's encrypted storage (Keystore-backed).
class SecureTokenStore implements RefreshTokenStore {
  const SecureTokenStore([this._storage = const FlutterSecureStorage()]);

  static const _key = 'caf.refresh_token';
  final FlutterSecureStorage _storage;

  @override
  bool get usesCookie => false;

  @override
  Future<String?> read() => _storage.read(key: _key);

  @override
  Future<void> write(String token) => _storage.write(key: _key, value: token);

  @override
  Future<void> clear() => _storage.delete(key: _key);
}

final refreshTokenStoreProvider = Provider<RefreshTokenStore>(
  (ref) => kIsWeb ? const CookieTokenStore() : const SecureTokenStore(),
);
