import 'dart:convert';
import 'dart:typed_data';

import 'package:caf_app/api/api.dart';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

/// What the fake server answers with.
class Reply {
  const Reply(this.status, [this.body, this.headers = const {}]);

  final int status;
  final Object? body;
  final Map<String, String> headers;
}

/// One request as it reached the server. Dio reuses the same options object
/// when a request is repeated, so the headers are copied on arrival.
class Seen {
  Seen(this.options)
    : method = options.method,
      path = options.path,
      headers = Map.of(options.headers),
      data = options.data == null ? null : jsonDecode(jsonEncode(options.data));

  final RequestOptions options;
  final String method;
  final String path;
  final Map<String, Object?> headers;
  final Object? data;

  String? get authorization => headers['Authorization'] as String?;
}

/// Stands in for caf-api: [handler] decides each reply, or throws a
/// [DioException] to act as a network failure.
class FakeServer implements HttpClientAdapter {
  FakeServer(this.handler);

  Reply Function(Seen request) handler;
  final requests = <Seen>[];

  Iterable<Seen> to(String path) => requests.where((r) => r.path == path);

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    final seen = Seen(options);
    requests.add(seen);
    final reply = handler(seen);
    return ResponseBody.fromString(
      reply.body == null ? '' : jsonEncode(reply.body),
      reply.status,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
        for (final entry in reply.headers.entries) entry.key: [entry.value],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

DioException networkFailure(Seen request) {
  return DioException.connectionError(
    requestOptions: request.options,
    reason: 'connection refused',
  );
}

Map<String, Object?> tokens(
  String role, {
  String access = 'access-1',
  String refresh = 'refresh-1',
}) {
  return {
    'access_token': access,
    'refresh_token': refresh,
    'token_type': 'bearer',
    'expires_in': 900,
    'role': role,
  };
}

const loginUrl = '/api/v1/auth/login';
const registerUrl = '/api/v1/auth/register';
const refreshUrl = '/api/v1/auth/refresh';
const logoutUrl = '/api/v1/auth/logout';
const meUrl = '/api/v1/auth/me';
const ordersUrl = '/api/v1/orders';

/// A provider container whose API calls go to [server]. Retry waits are
/// recorded in [delays] instead of being slept.
ProviderContainer containerFor(FakeServer server, {List<Duration>? delays}) {
  final container = ProviderContainer(
    overrides: [
      retryDelayProvider.overrideWithValue((delay) async => delays?.add(delay)),
    ],
  );
  addTearDown(container.dispose);
  container.read(dioProvider).httpClientAdapter = server;
  return container;
}
