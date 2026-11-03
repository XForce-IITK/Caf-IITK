// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'role.dart';

part 'staff_create.g.dart';

/// FR-2: a Kitchen Staff or Administrator account, created by an Administrator.
@JsonSerializable()
class StaffCreate {
  const StaffCreate({
    required this.email,
    required this.name,
    required this.password,
    required this.role,
  });

  factory StaffCreate.fromJson(Map<String, Object?> json) =>
      _$StaffCreateFromJson(json);

  final String email;
  final String name;
  final String password;
  final Role role;

  Map<String, Object?> toJson() => _$StaffCreateToJson(this);
}
