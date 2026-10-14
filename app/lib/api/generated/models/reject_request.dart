// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

part 'reject_request.g.dart';

@JsonSerializable()
class RejectRequest {
  const RejectRequest({required this.reason});

  factory RejectRequest.fromJson(Map<String, Object?> json) =>
      _$RejectRequestFromJson(json);

  final String reason;

  Map<String, Object?> toJson() => _$RejectRequestToJson(this);
}
