// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:dio/dio.dart';
import 'package:retrofit/retrofit.dart';

import '../models/agent_run_detail_out.dart';
import '../models/agent_run_out.dart';

part 'agent_client.g.dart';

@RestApi()
abstract class AgentClient {
  factory AgentClient(Dio dio, {String? baseUrl}) = _AgentClient;

  /// List Agent Runs.
  ///
  /// FR-63: run history, newest first.
  @GET('/api/v1/admin/agent/runs')
  Future<List<AgentRunOut>> listAgentRuns();

  /// Trigger Agent Run.
  ///
  /// FR-50: queue an on-demand planning run; caf-worker executes it within seconds.
  ///
  /// Only one run is in progress at a time: while one is QUEUED or RUNNING this.
  /// answers 409 with that run's ID.
  @POST('/api/v1/admin/agent/runs')
  Future<AgentRunOut> triggerAgentRun();

  /// Get Agent Run.
  ///
  /// FR-63: one run with its report, proposals and tool-call log.
  @GET('/api/v1/admin/agent/runs/{run_id}')
  Future<AgentRunDetailOut> getAgentRun({
    @Path('run_id') required String runId,
  });
}
