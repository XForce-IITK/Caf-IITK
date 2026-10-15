// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'quote_line_in.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

QuoteLineIn _$QuoteLineInFromJson(Map<String, dynamic> json) => QuoteLineIn(
  itemId: json['item_id'] as String,
  qty: (json['qty'] as num).toInt(),
);

Map<String, dynamic> _$QuoteLineInToJson(QuoteLineIn instance) =>
    <String, dynamic>{'item_id': instance.itemId, 'qty': instance.qty};
