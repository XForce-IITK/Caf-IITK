// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'quote_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

QuoteOut _$QuoteOutFromJson(Map<String, dynamic> json) => QuoteOut(
  discountedSubtotalPaise: (json['discounted_subtotal_paise'] as num).toInt(),
  lines: (json['lines'] as List<dynamic>)
      .map((e) => QuoteLineOut.fromJson(e as Map<String, dynamic>))
      .toList(),
  payablePaise: (json['payable_paise'] as num).toInt(),
  roundingAdjustmentPaise: (json['rounding_adjustment_paise'] as num).toInt(),
  slotId: json['slot_id'] as String,
  subsidyPaise: (json['subsidy_paise'] as num).toInt(),
);

Map<String, dynamic> _$QuoteOutToJson(QuoteOut instance) => <String, dynamic>{
  'discounted_subtotal_paise': instance.discountedSubtotalPaise,
  'lines': instance.lines,
  'payable_paise': instance.payablePaise,
  'rounding_adjustment_paise': instance.roundingAdjustmentPaise,
  'slot_id': instance.slotId,
  'subsidy_paise': instance.subsidyPaise,
};
