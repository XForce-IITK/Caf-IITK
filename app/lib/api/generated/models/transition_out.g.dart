// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'transition_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

TransitionOut _$TransitionOutFromJson(Map<String, dynamic> json) =>
    TransitionOut(
      actorRole: json['actor_role'] == null
          ? null
          : Role.fromJson(json['actor_role'] as String),
      at: DateTime.parse(json['at'] as String),
      fromStatus: json['from_status'] == null
          ? null
          : OrderStatus.fromJson(json['from_status'] as String),
      reason: json['reason'] as String?,
      toStatus: OrderStatus.fromJson(json['to_status'] as String),
    );

Map<String, dynamic> _$TransitionOutToJson(TransitionOut instance) =>
    <String, dynamic>{
      'actor_role': instance.actorRole,
      'at': instance.at.toIso8601String(),
      'from_status': instance.fromStatus,
      'reason': instance.reason,
      'to_status': instance.toStatus,
    };
