import 'package:dio/dio.dart';

import '../auth/session.dart';
import 'ids.dart';

const _authPrefix = '/api/v1/auth/';
const _publicPaths = {
  '${_authPrefix}login',
  '${_authPrefix}register',
  '${_authPrefix}refresh',
};
const _retriedAfterRefresh = 'caf.retriedAfterRefresh';
const _retryAttempt = 'caf.retryAttempt';

/// Gives every request a fresh X-Request-ID (NFR-29).
class RequestIdInterceptor extends Interceptor {
  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    options.headers['X-Request-ID'] = newUuid();
    handler.next(options);
  }
}

/// Attaches the access token and, on a 401, refreshes it once and repeats the
/// request. A failed refresh ends the session.
class AuthInterceptor extends Interceptor {
  AuthInterceptor({
    required this.dio,
    required this.readSession,
    required this.refreshSession,
  });

  final Dio dio;
  final Session? Function() readSession;
  final Future<bool> Function() refreshSession;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    final session = readSession();
    if (session != null && !_publicPaths.contains(options.path)) {
      options.headers['Authorization'] = 'Bearer ${session.accessToken}';
    }
    handler.next(options);
  }

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    final options = err.requestOptions;
    final canRefresh =
        err.response?.statusCode == 401 &&
        !_publicPaths.contains(options.path) &&
        options.extra[_retriedAfterRefresh] != true &&
        readSession() != null;
    if (!canRefresh || !await refreshSession()) {
      return handler.next(err);
    }
    options.extra[_retriedAfterRefresh] = true;
    try {
      handler.resolve(await dio.fetch<dynamic>(options));
    } on DioException catch (retryError) {
      handler.next(retryError);
    }
  }
}

/// Waits before a retry. Replaced in tests so they do not sleep.
typedef RetryDelay = Future<void> Function(Duration delay);

/// NFR-18: a create, modify or cancel request (one that carries an
/// Idempotency-Key) is retried at most [maxRetries] times with exponential
/// back-off when the network fails or the server is briefly unavailable. The
/// key is reused, so the server applies the action once.
class IdempotentRetryInterceptor extends Interceptor {
  IdempotentRetryInterceptor({
    required this.dio,
    this.delay = Future<void>.delayed,
    this.baseDelay = const Duration(milliseconds: 500),
  });

  static const maxRetries = 3;
  static const _retryableStatuses = {502, 503, 504};
  static const _retryableTypes = {
    DioExceptionType.connectionError,
    DioExceptionType.connectionTimeout,
    DioExceptionType.sendTimeout,
    DioExceptionType.receiveTimeout,
  };

  final Dio dio;
  final RetryDelay delay;
  final Duration baseDelay;

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    final options = err.requestOptions;
    final attempt = (options.extra[_retryAttempt] as int?) ?? 0;
    final retryable =
        options.headers.containsKey('Idempotency-Key') &&
        attempt < maxRetries &&
        (_retryableTypes.contains(err.type) ||
            _retryableStatuses.contains(err.response?.statusCode));
    if (!retryable) {
      return handler.next(err);
    }
    await delay(_backOff(attempt, err.response));
    options.extra[_retryAttempt] = attempt + 1;
    try {
      handler.resolve(await dio.fetch<dynamic>(options));
    } on DioException catch (retryError) {
      handler.next(retryError);
    }
  }

  /// 0.5 s, 1 s, 2 s, or the server's Retry-After if that is longer.
  Duration _backOff(int attempt, Response<dynamic>? response) {
    final exponential = baseDelay * (1 << attempt);
    final seconds = int.tryParse(response?.headers.value('retry-after') ?? '');
    if (seconds == null) return exponential;
    final requested = Duration(seconds: seconds);
    return requested > exponential ? requested : exponential;
  }
}
