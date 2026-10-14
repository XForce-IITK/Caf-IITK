// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

part 'cancel_order_request.g.dart';

/// The order version the Student saw when confirming (NFR-5).
@JsonSerializable()
class CancelOrderRequest {
  const CancelOrderRequest({required this.version});

  factory CancelOrderRequest.fromJson(Map<String, Object?> json) =>
      _$CancelOrderRequestFromJson(json);

  final int version;

  Map<String, Object?> toJson() => _$CancelOrderRequestToJson(this);
}
