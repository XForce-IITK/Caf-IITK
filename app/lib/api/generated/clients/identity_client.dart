// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:dio/dio.dart';
import 'package:retrofit/retrofit.dart';

import '../models/account_out.dart';
import '../models/login_request.dart';
import '../models/refresh_request.dart';
import '../models/register_request.dart';
import '../models/staff_create.dart';
import '../models/token_pair.dart';
import '../models/user_out.dart';

part 'identity_client.g.dart';

@RestApi()
abstract class IdentityClient {
  factory IdentityClient(Dio dio, {String? baseUrl}) = _IdentityClient;

  /// List Staff Accounts.
  ///
  /// UC-03: every Kitchen Staff and Administrator account, active or not, by name.
  @GET('/api/v1/admin/users')
  Future<List<AccountOut>> listStaffAccounts();

  /// Create Staff Account.
  ///
  /// FR-2: create a Kitchen Staff or Administrator account. Students register.
  /// themselves, so role STUDENT is refused with 422.
  @POST('/api/v1/admin/users')
  Future<AccountOut> createStaffAccount({@Body() required StaffCreate body});

  /// Deactivate Account.
  ///
  /// FR-3: the account can no longer log in or refresh, and its access tokens are.
  /// refused at once. Deactivating an inactive account changes nothing.
  @POST('/api/v1/admin/users/{user_id}/deactivate')
  Future<AccountOut> deactivateAccount({
    @Path('user_id') required String userId,
  });

  /// Reactivate Account.
  ///
  /// FR-3: the account can log in again; its old refresh tokens stay revoked.
  @POST('/api/v1/admin/users/{user_id}/reactivate')
  Future<AccountOut> reactivateAccount({
    @Path('user_id') required String userId,
  });

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
