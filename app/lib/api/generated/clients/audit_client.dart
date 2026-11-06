// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:dio/dio.dart';
import 'package:retrofit/retrofit.dart';

import '../models/audit_page_out.dart';

part 'audit_client.g.dart';

@RestApi()
abstract class AuditClient {
  factory AuditClient(Dio dio, {String? baseUrl}) = _AuditClient;

  /// Search Audit.
  ///
  /// FR-49 / US-38: search the append-only audit log by time range, actor, entity.
  /// and action, newest first, a page at a time. Secrets never appear in results.
  ///
  /// [from] - Inclusive.
  ///
  /// [to] - Exclusive.
  ///
  /// [entityId] - Also matches entries that name this ID as their order.
  ///
  /// [beforeId] - next_before_id of the previous page.
  @GET('/api/v1/admin/audit')
  Future<AuditPageOut> searchAudit({
    @Query('limit') int? limit = 50,
    @Query('from') DateTime? from,
    @Query('to') DateTime? to,
    @Query('actor_id') String? actorId,
    @Query('entity_type') String? entityType,
    @Query('entity_id') String? entityId,
    @Query('action') String? action,
    @Query('before_id') int? beforeId,
  });
}
