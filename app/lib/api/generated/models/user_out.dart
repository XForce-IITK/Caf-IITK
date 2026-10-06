// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'role.dart';

part 'user_out.g.dart';

@JsonSerializable()
class UserOut {
  const UserOut({
    required this.email,
    required this.id,
    required this.name,
    required this.role,
  });
  
  factory UserOut.fromJson(Map<String, Object?> json) => _$UserOutFromJson(json);
  
  final String email;
  final String id;
  final String name;
  final Role role;

  Map<String, Object?> toJson() => _$UserOutToJson(this);
}
