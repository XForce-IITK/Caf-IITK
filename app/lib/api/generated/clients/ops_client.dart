// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:dio/dio.dart';
import 'package:retrofit/retrofit.dart';

part 'ops_client.g.dart';

@RestApi()
abstract class OpsClient {
  factory OpsClient(Dio dio, {String? baseUrl}) = _OpsClient;

  /// Health
  @GET('/health')
  Future<Map<String, String>> health();
}
