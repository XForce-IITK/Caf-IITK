// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'place_order_request.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

PlaceOrderRequest _$PlaceOrderRequestFromJson(Map<String, dynamic> json) =>
    PlaceOrderRequest(
      lines: (json['lines'] as List<dynamic>)
          .map((e) => QuoteLineIn.fromJson(e as Map<String, dynamic>))
          .toList(),
      quotedPayablePaise: (json['quoted_payable_paise'] as num).toInt(),
      slotId: json['slot_id'] as String,
    );

Map<String, dynamic> _$PlaceOrderRequestToJson(PlaceOrderRequest instance) =>
    <String, dynamic>{
      'lines': instance.lines,
      'quoted_payable_paise': instance.quotedPayablePaise,
      'slot_id': instance.slotId,
    };
