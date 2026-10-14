// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'order_status.dart';
import 'role.dart';

part 'transition_out.g.dart';

@JsonSerializable()
class TransitionOut {
  const TransitionOut({
    required this.actorRole,
    required this.at,
    required this.fromStatus,
    required this.reason,
    required this.toStatus,
  });

  factory TransitionOut.fromJson(Map<String, Object?> json) =>
      _$TransitionOutFromJson(json);

  @JsonKey(name: 'actor_role')
  final Role? actorRole;
  final DateTime at;
  @JsonKey(name: 'from_status')
  final OrderStatus? fromStatus;
  final String? reason;
  @JsonKey(name: 'to_status')
  final OrderStatus toStatus;

  Map<String, Object?> toJson() => _$TransitionOutToJson(this);
}
