// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'order_status.dart';
import 'quote_out.dart';

part 'admin_order_out.g.dart';

/// FR-45: an order as the Administrator sees it, with who placed it and when it is due.
@JsonSerializable()
class AdminOrderOut {
  const AdminOrderOut({
    required this.createdAt,
    required this.id,
    required this.paidPaise,
    required this.price,
    required this.slotId,
    required this.slotStartsAt,
    required this.status,
    required this.studentEmail,
    required this.studentId,
    required this.studentName,
    required this.subsidyApplied,
    required this.version,
  });

  factory AdminOrderOut.fromJson(Map<String, Object?> json) =>
      _$AdminOrderOutFromJson(json);

  @JsonKey(name: 'created_at')
  final DateTime createdAt;
  final String id;
  @JsonKey(name: 'paid_paise')
  final int paidPaise;
  final QuoteOut price;
  @JsonKey(name: 'slot_id')
  final String slotId;
  @JsonKey(name: 'slot_starts_at')
  final DateTime slotStartsAt;
  final OrderStatus status;
  @JsonKey(name: 'student_email')
  final String studentEmail;
  @JsonKey(name: 'student_id')
  final String studentId;
  @JsonKey(name: 'student_name')
  final String studentName;
  @JsonKey(name: 'subsidy_applied')
  final bool subsidyApplied;
  final int version;

  Map<String, Object?> toJson() => _$AdminOrderOutToJson(this);
}
