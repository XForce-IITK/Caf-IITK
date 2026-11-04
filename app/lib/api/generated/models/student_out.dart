// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

part 'student_out.g.dart';

@JsonSerializable()
class StudentOut {
  const StudentOut({
    required this.email,
    required this.id,
    required this.isActive,
    required this.name,
    required this.subsidyEligible,
  });

  factory StudentOut.fromJson(Map<String, Object?> json) =>
      _$StudentOutFromJson(json);

  final String email;
  final String id;
  @JsonKey(name: 'is_active')
  final bool isActive;
  final String name;
  @JsonKey(name: 'subsidy_eligible')
  final bool subsidyEligible;

  Map<String, Object?> toJson() => _$StudentOutToJson(this);
}
