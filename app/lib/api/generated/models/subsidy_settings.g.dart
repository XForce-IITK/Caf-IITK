// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'subsidy_settings.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

SubsidySettings _$SubsidySettingsFromJson(Map<String, dynamic> json) =>
    SubsidySettings(
      amountPaise: (json['amount_paise'] as num).toInt(),
      capPct: (json['cap_pct'] as num).toInt(),
    );

Map<String, dynamic> _$SubsidySettingsToJson(SubsidySettings instance) =>
    <String, dynamic>{
      'amount_paise': instance.amountPaise,
      'cap_pct': instance.capPct,
    };
