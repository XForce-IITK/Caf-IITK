import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'generated/export.dart';

export 'generated/export.dart';

/// Where caf-api is served. Override at build time with
/// `--dart-define=API_BASE_URL=https://...`.
const apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://localhost:8000',
);

/// The single Dio instance behind every API call. Token refresh, X-Request-ID,
/// Idempotency-Key and retry interceptors are added under CAFIITK-177.
final dioProvider = Provider<Dio>((ref) {
  final dio = Dio(BaseOptions(baseUrl: apiBaseUrl));
  ref.onDispose(dio.close);
  return dio;
});

/// The API client generated from caf-api's OpenAPI schema (NFR-39).
final apiProvider = Provider<CafApi>((ref) => CafApi(ref.watch(dioProvider)));

/// The API takes service dates as plain dates. The generated client sends a
/// [DateTime], which the backend accepts only when its time is midnight.
DateTime serviceDate(DateTime moment) =>
    DateTime(moment.year, moment.month, moment.day);
