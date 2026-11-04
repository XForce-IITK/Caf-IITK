// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

part 'eligibility_update.g.dart';

@JsonSerializable()
class EligibilityUpdate {
  const EligibilityUpdate({required this.eligible});

  factory EligibilityUpdate.fromJson(Map<String, Object?> json) =>
      _$EligibilityUpdateFromJson(json);

  final bool eligible;

  Map<String, Object?> toJson() => _$EligibilityUpdateToJson(this);
}
