// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'tool_call_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

ToolCallOut _$ToolCallOutFromJson(Map<String, dynamic> json) => ToolCallOut(
  args: json['args'],
  latencyMs: (json['latency_ms'] as num?)?.toInt(),
  outcome: json['outcome'] as String,
  resultSummary: json['result_summary'] as String?,
  seq: (json['seq'] as num).toInt(),
  tool: json['tool'] as String,
);

Map<String, dynamic> _$ToolCallOutToJson(ToolCallOut instance) =>
    <String, dynamic>{
      'args': instance.args,
      'latency_ms': instance.latencyMs,
      'outcome': instance.outcome,
      'result_summary': instance.resultSummary,
      'seq': instance.seq,
      'tool': instance.tool,
    };
