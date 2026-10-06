// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'token_pair.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

TokenPair _$TokenPairFromJson(Map<String, dynamic> json) => TokenPair(
  accessToken: json['access_token'] as String,
  expiresIn: (json['expires_in'] as num).toInt(),
  refreshToken: json['refresh_token'] as String,
  role: Role.fromJson(json['role'] as String),
  tokenType: json['token_type'] as String? ?? 'bearer',
);

Map<String, dynamic> _$TokenPairToJson(TokenPair instance) => <String, dynamic>{
  'access_token': instance.accessToken,
  'expires_in': instance.expiresIn,
  'refresh_token': instance.refreshToken,
  'role': instance.role,
  'token_type': instance.tokenType,
};
