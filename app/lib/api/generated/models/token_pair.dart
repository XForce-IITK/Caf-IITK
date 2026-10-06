// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'role.dart';

part 'token_pair.g.dart';

@JsonSerializable()
class TokenPair {
  const TokenPair({
    required this.accessToken,
    required this.expiresIn,
    required this.refreshToken,
    required this.role,
    this.tokenType = 'bearer',
  });

  factory TokenPair.fromJson(Map<String, Object?> json) =>
      _$TokenPairFromJson(json);

  @JsonKey(name: 'access_token')
  final String accessToken;
  @JsonKey(name: 'expires_in')
  final int expiresIn;
  @JsonKey(name: 'refresh_token')
  final String refreshToken;
  final Role role;
  @JsonKey(name: 'token_type')
  final String tokenType;

  Map<String, Object?> toJson() => _$TokenPairToJson(this);
}
