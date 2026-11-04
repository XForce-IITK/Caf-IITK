// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

part 'subsidy_settings.g.dart';

/// FR-23: P-SUBSIDY_AMT and P-SUBSIDY_CAP_PCT.
///
/// An eligible Student's first subsidised order of a day gets.
/// min(amount_paise, cap_pct % of the discounted subtotal) off (FR-24 step 4).
@JsonSerializable()
class SubsidySettings {
  const SubsidySettings({required this.amountPaise, required this.capPct});

  factory SubsidySettings.fromJson(Map<String, Object?> json) =>
      _$SubsidySettingsFromJson(json);

  @JsonKey(name: 'amount_paise')
  final int amountPaise;
  @JsonKey(name: 'cap_pct')
  final int capPct;

  Map<String, Object?> toJson() => _$SubsidySettingsToJson(this);
}
