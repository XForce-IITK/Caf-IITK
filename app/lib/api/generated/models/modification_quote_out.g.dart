// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'modification_quote_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

ModificationQuoteOut _$ModificationQuoteOutFromJson(
  Map<String, dynamic> json,
) => ModificationQuoteOut(
  differencePaise: (json['difference_paise'] as num).toInt(),
  paidPaise: (json['paid_paise'] as num).toInt(),
  quote: QuoteOut.fromJson(json['quote'] as Map<String, dynamic>),
);

Map<String, dynamic> _$ModificationQuoteOutToJson(
  ModificationQuoteOut instance,
) => <String, dynamic>{
  'difference_paise': instance.differencePaise,
  'paid_paise': instance.paidPaise,
  'quote': instance.quote,
};
