// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'admin_order_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

AdminOrderOut _$AdminOrderOutFromJson(Map<String, dynamic> json) =>
    AdminOrderOut(
      createdAt: DateTime.parse(json['created_at'] as String),
      id: json['id'] as String,
      paidPaise: (json['paid_paise'] as num).toInt(),
      price: QuoteOut.fromJson(json['price'] as Map<String, dynamic>),
      slotId: json['slot_id'] as String,
      slotStartsAt: DateTime.parse(json['slot_starts_at'] as String),
      status: OrderStatus.fromJson(json['status'] as String),
      studentEmail: json['student_email'] as String,
      studentId: json['student_id'] as String,
      studentName: json['student_name'] as String,
      subsidyApplied: json['subsidy_applied'] as bool,
      version: (json['version'] as num).toInt(),
    );

Map<String, dynamic> _$AdminOrderOutToJson(AdminOrderOut instance) =>
    <String, dynamic>{
      'created_at': instance.createdAt.toIso8601String(),
      'id': instance.id,
      'paid_paise': instance.paidPaise,
      'price': instance.price,
      'slot_id': instance.slotId,
      'slot_starts_at': instance.slotStartsAt.toIso8601String(),
      'status': instance.status,
      'student_email': instance.studentEmail,
      'student_id': instance.studentId,
      'student_name': instance.studentName,
      'subsidy_applied': instance.subsidyApplied,
      'version': instance.version,
    };
