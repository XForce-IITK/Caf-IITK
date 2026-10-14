// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'user_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

UserOut _$UserOutFromJson(Map<String, dynamic> json) => UserOut(
  email: json['email'] as String,
  id: json['id'] as String,
  name: json['name'] as String,
  role: Role.fromJson(json['role'] as String),
);

Map<String, dynamic> _$UserOutToJson(UserOut instance) => <String, dynamic>{
  'email': instance.email,
  'id': instance.id,
  'name': instance.name,
  'role': instance.role,
};
