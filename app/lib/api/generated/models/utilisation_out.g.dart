// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'utilisation_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

UtilisationOut _$UtilisationOutFromJson(Map<String, dynamic> json) =>
    UtilisationOut(
      asOf: DateTime.parse(json['as_of'] as String),
      items: (json['items'] as List<dynamic>)
          .map((e) => ItemUtilisationOut.fromJson(e as Map<String, dynamic>))
          .toList(),
      orderCounts: Map<String, int>.from(json['order_counts'] as Map),
      serviceDate: DateTime.parse(json['service_date'] as String),
      slots: (json['slots'] as List<dynamic>)
          .map((e) => SlotUtilisationOut.fromJson(e as Map<String, dynamic>))
          .toList(),
    );

Map<String, dynamic> _$UtilisationOutToJson(UtilisationOut instance) =>
    <String, dynamic>{
      'as_of': instance.asOf.toIso8601String(),
      'items': instance.items,
      'order_counts': instance.orderCounts,
      'service_date': instance.serviceDate.toIso8601String(),
      'slots': instance.slots,
    };
