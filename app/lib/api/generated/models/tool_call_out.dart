// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

part 'tool_call_out.g.dart';

@JsonSerializable()
class ToolCallOut {
  const ToolCallOut({
    required this.args,
    required this.latencyMs,
    required this.outcome,
    required this.resultSummary,
    required this.seq,
    required this.tool,
  });

  factory ToolCallOut.fromJson(Map<String, Object?> json) =>
      _$ToolCallOutFromJson(json);

  final dynamic args;
  @JsonKey(name: 'latency_ms')
  final int? latencyMs;
  final String outcome;
  @JsonKey(name: 'result_summary')
  final String? resultSummary;
  final int seq;
  final String tool;

  Map<String, Object?> toJson() => _$ToolCallOutToJson(this);
}
