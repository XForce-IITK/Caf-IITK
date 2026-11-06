// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'account_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

AccountOut _$AccountOutFromJson(Map<String, dynamic> json) => AccountOut(
  email: json['email'] as String,
  id: json['id'] as String,
  isActive: json['is_active'] as bool,
  name: json['name'] as String,
  role: Role.fromJson(json['role'] as String),
);

Map<String, dynamic> _$AccountOutToJson(AccountOut instance) =>
    <String, dynamic>{
      'email': instance.email,
      'id': instance.id,
      'is_active': instance.isActive,
      'name': instance.name,
      'role': instance.role,
    };
