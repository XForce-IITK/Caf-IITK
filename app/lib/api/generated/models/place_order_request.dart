// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'quote_line_in.dart';

part 'place_order_request.g.dart';

/// The cart and slot that were quoted, plus the amount the Student agreed to (FR-26).
@JsonSerializable()
class PlaceOrderRequest {
  const PlaceOrderRequest({
    required this.lines,
    required this.quotedPayablePaise,
    required this.slotId,
  });

  factory PlaceOrderRequest.fromJson(Map<String, Object?> json) =>
      _$PlaceOrderRequestFromJson(json);

  final List<QuoteLineIn> lines;
  @JsonKey(name: 'quoted_payable_paise')
  final int quotedPayablePaise;
  @JsonKey(name: 'slot_id')
  final String slotId;

  Map<String, Object?> toJson() => _$PlaceOrderRequestToJson(this);
}
