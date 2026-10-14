// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'quote_request.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

QuoteRequest _$QuoteRequestFromJson(Map<String, dynamic> json) => QuoteRequest(
  lines: (json['lines'] as List<dynamic>)
      .map((e) => QuoteLineIn.fromJson(e as Map<String, dynamic>))
      .toList(),
  slotId: json['slot_id'] as String,
);

Map<String, dynamic> _$QuoteRequestToJson(QuoteRequest instance) =>
    <String, dynamic>{'lines': instance.lines, 'slot_id': instance.slotId};
