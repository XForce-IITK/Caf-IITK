// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'student_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

StudentOut _$StudentOutFromJson(Map<String, dynamic> json) => StudentOut(
  email: json['email'] as String,
  id: json['id'] as String,
  isActive: json['is_active'] as bool,
  name: json['name'] as String,
  subsidyEligible: json['subsidy_eligible'] as bool,
);

Map<String, dynamic> _$StudentOutToJson(StudentOut instance) =>
    <String, dynamic>{
      'email': instance.email,
      'id': instance.id,
      'is_active': instance.isActive,
      'name': instance.name,
      'subsidy_eligible': instance.subsidyEligible,
    };
