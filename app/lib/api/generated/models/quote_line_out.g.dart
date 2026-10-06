// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'quote_line_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

QuoteLineOut _$QuoteLineOutFromJson(Map<String, dynamic> json) => QuoteLineOut(
  discountPct: (json['discount_pct'] as num).toInt(),
  itemId: json['item_id'] as String,
  lineBasePaise: (json['line_base_paise'] as num).toInt(),
  lineDiscountPaise: (json['line_discount_paise'] as num).toInt(),
  lineTotalPaise: (json['line_total_paise'] as num).toInt(),
  name: json['name'] as String,
  qty: (json['qty'] as num).toInt(),
  ruleId: json['rule_id'] as String?,
  unitPricePaise: (json['unit_price_paise'] as num).toInt(),
);

Map<String, dynamic> _$QuoteLineOutToJson(QuoteLineOut instance) =>
    <String, dynamic>{
      'discount_pct': instance.discountPct,
      'item_id': instance.itemId,
      'line_base_paise': instance.lineBasePaise,
      'line_discount_paise': instance.lineDiscountPaise,
      'line_total_paise': instance.lineTotalPaise,
      'name': instance.name,
      'qty': instance.qty,
      'rule_id': instance.ruleId,
      'unit_price_paise': instance.unitPricePaise,
    };
