// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'modify_order_request.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

ModifyOrderRequest _$ModifyOrderRequestFromJson(Map<String, dynamic> json) =>
    ModifyOrderRequest(
      lines: (json['lines'] as List<dynamic>)
          .map((e) => QuoteLineIn.fromJson(e as Map<String, dynamic>))
          .toList(),
      quotedPayablePaise: (json['quoted_payable_paise'] as num).toInt(),
      slotId: json['slot_id'] as String,
      version: (json['version'] as num).toInt(),
    );

Map<String, dynamic> _$ModifyOrderRequestToJson(ModifyOrderRequest instance) =>
    <String, dynamic>{
      'lines': instance.lines,
      'quoted_payable_paise': instance.quotedPayablePaise,
      'slot_id': instance.slotId,
      'version': instance.version,
    };
