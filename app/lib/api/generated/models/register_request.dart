// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

part 'register_request.g.dart';

@JsonSerializable()
class RegisterRequest {
  const RegisterRequest({
    required this.email,
    required this.name,
    required this.password,
  });
  
  factory RegisterRequest.fromJson(Map<String, Object?> json) => _$RegisterRequestFromJson(json);
  
  final String email;
  final String name;
  final String password;

  Map<String, Object?> toJson() => _$RegisterRequestToJson(this);
}
