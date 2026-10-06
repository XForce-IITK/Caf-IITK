// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:dio/dio.dart';
import 'package:retrofit/retrofit.dart';

import '../models/login_request.dart';
import '../models/refresh_request.dart';
import '../models/register_request.dart';
import '../models/token_pair.dart';
import '../models/user_out.dart';

part 'identity_client.g.dart';

@RestApi()
abstract class IdentityClient {
  factory IdentityClient(Dio dio, {String? baseUrl}) = _IdentityClient;

  /// Login
  @POST('/api/v1/auth/login')
  Future<TokenPair> login({@Body() required LoginRequest body});

  /// Logout
  @POST('/api/v1/auth/logout')
  Future<void> logout({@Body() required RefreshRequest body});

  /// Me
  @GET('/api/v1/auth/me')
  Future<UserOut> me();

  /// Refresh
  @POST('/api/v1/auth/refresh')
  Future<TokenPair> refresh({@Body() required RefreshRequest body});

  /// Register
  @POST('/api/v1/auth/register')
  Future<UserOut> register({@Body() required RegisterRequest body});
}
