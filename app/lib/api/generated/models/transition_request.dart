// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'kitchen_action.dart';

part 'transition_request.g.dart';

@JsonSerializable()
class TransitionRequest {
  const TransitionRequest({required this.action});

  factory TransitionRequest.fromJson(Map<String, Object?> json) =>
      _$TransitionRequestFromJson(json);

  final KitchenAction action;

  Map<String, Object?> toJson() => _$TransitionRequestToJson(this);
}
