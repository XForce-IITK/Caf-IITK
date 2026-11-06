// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'audit_page_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

AuditPageOut _$AuditPageOutFromJson(Map<String, dynamic> json) => AuditPageOut(
  entries: (json['entries'] as List<dynamic>)
      .map((e) => AuditEntryOut.fromJson(e as Map<String, dynamic>))
      .toList(),
  nextBeforeId: (json['next_before_id'] as num?)?.toInt(),
);

Map<String, dynamic> _$AuditPageOutToJson(AuditPageOut instance) =>
    <String, dynamic>{
      'entries': instance.entries,
      'next_before_id': instance.nextBeforeId,
    };
