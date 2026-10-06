// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

part 'quote_line_out.g.dart';

@JsonSerializable()
class QuoteLineOut {
  const QuoteLineOut({
    required this.discountPct,
    required this.itemId,
    required this.lineBasePaise,
    required this.lineDiscountPaise,
    required this.lineTotalPaise,
    required this.name,
    required this.qty,
    required this.ruleId,
    required this.unitPricePaise,
  });

  factory QuoteLineOut.fromJson(Map<String, Object?> json) =>
      _$QuoteLineOutFromJson(json);

  @JsonKey(name: 'discount_pct')
  final int discountPct;
  @JsonKey(name: 'item_id')
  final String itemId;
  @JsonKey(name: 'line_base_paise')
  final int lineBasePaise;
  @JsonKey(name: 'line_discount_paise')
  final int lineDiscountPaise;
  @JsonKey(name: 'line_total_paise')
  final int lineTotalPaise;
  final String name;
  final int qty;
  @JsonKey(name: 'rule_id')
  final String? ruleId;
  @JsonKey(name: 'unit_price_paise')
  final int unitPricePaise;

  Map<String, Object?> toJson() => _$QuoteLineOutToJson(this);
}
