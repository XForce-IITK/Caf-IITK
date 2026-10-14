import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/session.dart';
import 'generated/export.dart';
import 'interceptors.dart';

export 'generated/export.dart';
export 'ids.dart';
export 'interceptors.dart' show RetryDelay;

/// Where caf-api is served. Override at build time with
/// `--dart-define=API_BASE_URL=https://...`.
const apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://localhost:8000',
);

/// How long to wait before a retry (NFR-18). Overridden in tests.
final retryDelayProvider = Provider<RetryDelay>((ref) => Future<void>.delayed);

/// The single Dio instance behind every API call. Its interceptors attach the
/// access token (refreshing it once on a 401) and a fresh X-Request-ID, and
/// retry requests that carry an Idempotency-Key.
final dioProvider = Provider<Dio>((ref) {
  final dio = Dio(BaseOptions(baseUrl: apiBaseUrl));
  dio.interceptors.addAll([
    RequestIdInterceptor(),
    AuthInterceptor(
      dio: dio,
      readSession: () => ref.read(sessionProvider),
      refreshSession: () => ref.read(sessionProvider.notifier).refresh(),
    ),
    IdempotentRetryInterceptor(dio: dio, delay: ref.watch(retryDelayProvider)),
  ]);
  ref.onDispose(dio.close);
  return dio;
});

/// The API client generated from caf-api's OpenAPI schema (NFR-39).
final apiProvider = Provider<CafApi>((ref) => CafApi(ref.watch(dioProvider)));

/// The API takes service dates as plain dates. The generated client sends a
/// [DateTime], which the backend accepts only when its time is midnight.
DateTime serviceDate(DateTime moment) =>
    DateTime(moment.year, moment.month, moment.day);
