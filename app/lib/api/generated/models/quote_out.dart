// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'quote_line_out.dart';

part 'quote_out.g.dart';

/// The full FR-24 breakdown. Amounts are integer paise.
@JsonSerializable()
class QuoteOut {
  const QuoteOut({
    required this.discountedSubtotalPaise,
    required this.lines,
    required this.payablePaise,
    required this.roundingAdjustmentPaise,
    required this.slotId,
    required this.subsidyPaise,
  });
  
  factory QuoteOut.fromJson(Map<String, Object?> json) => _$QuoteOutFromJson(json);
  
  @JsonKey(name: 'discounted_subtotal_paise')
  final int discountedSubtotalPaise;
  final List<QuoteLineOut> lines;
  @JsonKey(name: 'payable_paise')
  final int payablePaise;
  @JsonKey(name: 'rounding_adjustment_paise')
  final int roundingAdjustmentPaise;
  @JsonKey(name: 'slot_id')
  final String slotId;
  @JsonKey(name: 'subsidy_paise')
  final int subsidyPaise;

  Map<String, Object?> toJson() => _$QuoteOutToJson(this);
}
