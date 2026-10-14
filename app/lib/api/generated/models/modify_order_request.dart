// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'quote_line_in.dart';

part 'modify_order_request.g.dart';

/// The complete new cart and slot (UC-12), as quoted, and the version the Student saw.
@JsonSerializable()
class ModifyOrderRequest {
  const ModifyOrderRequest({
    required this.lines,
    required this.quotedPayablePaise,
    required this.slotId,
    required this.version,
  });

  factory ModifyOrderRequest.fromJson(Map<String, Object?> json) =>
      _$ModifyOrderRequestFromJson(json);

  final List<QuoteLineIn> lines;
  @JsonKey(name: 'quoted_payable_paise')
  final int quotedPayablePaise;
  @JsonKey(name: 'slot_id')
  final String slotId;
  final int version;

  Map<String, Object?> toJson() => _$ModifyOrderRequestToJson(this);
}
