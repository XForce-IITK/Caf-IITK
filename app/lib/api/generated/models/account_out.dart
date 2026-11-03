// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'role.dart';

part 'account_out.g.dart';

@JsonSerializable()
class AccountOut {
  const AccountOut({
    required this.email,
    required this.id,
    required this.isActive,
    required this.name,
    required this.role,
  });

  factory AccountOut.fromJson(Map<String, Object?> json) =>
      _$AccountOutFromJson(json);

  final String email;
  final String id;
  @JsonKey(name: 'is_active')
  final bool isActive;
  final String name;
  final Role role;

  Map<String, Object?> toJson() => _$AccountOutToJson(this);
}
