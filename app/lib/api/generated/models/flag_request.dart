// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

part 'flag_request.g.dart';

@JsonSerializable()
class FlagRequest {
  const FlagRequest({required this.reason});

  factory FlagRequest.fromJson(Map<String, Object?> json) =>
      _$FlagRequestFromJson(json);

  final String reason;

  Map<String, Object?> toJson() => _$FlagRequestToJson(this);
}
