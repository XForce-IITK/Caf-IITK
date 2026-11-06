// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

part 'admin_cancel_order_request.g.dart';

/// FR-38: the Administrator must say why; whitespace alone is no reason.
@JsonSerializable()
class AdminCancelOrderRequest {
  const AdminCancelOrderRequest({required this.reason, required this.version});

  factory AdminCancelOrderRequest.fromJson(Map<String, Object?> json) =>
      _$AdminCancelOrderRequestFromJson(json);

  final String reason;
  final int version;

  Map<String, Object?> toJson() => _$AdminCancelOrderRequestToJson(this);
}
