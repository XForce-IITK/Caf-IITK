// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'snapshot_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

SnapshotOut _$SnapshotOutFromJson(Map<String, dynamic> json) => SnapshotOut(
  price: QuoteOut.fromJson(json['price'] as Map<String, dynamic>),
  pricedAt: DateTime.parse(json['priced_at'] as String),
  version: (json['version'] as num).toInt(),
);

Map<String, dynamic> _$SnapshotOutToJson(SnapshotOut instance) =>
    <String, dynamic>{
      'price': instance.price,
      'priced_at': instance.pricedAt.toIso8601String(),
      'version': instance.version,
    };
