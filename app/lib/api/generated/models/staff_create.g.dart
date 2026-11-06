// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'staff_create.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

StaffCreate _$StaffCreateFromJson(Map<String, dynamic> json) => StaffCreate(
  email: json['email'] as String,
  name: json['name'] as String,
  password: json['password'] as String,
  role: Role.fromJson(json['role'] as String),
);

Map<String, dynamic> _$StaffCreateToJson(StaffCreate instance) =>
    <String, dynamic>{
      'email': instance.email,
      'name': instance.name,
      'password': instance.password,
      'role': instance.role,
    };
