// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'admin_cancel_order_request.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

AdminCancelOrderRequest _$AdminCancelOrderRequestFromJson(
  Map<String, dynamic> json,
) => AdminCancelOrderRequest(
  reason: json['reason'] as String,
  version: (json['version'] as num).toInt(),
);

Map<String, dynamic> _$AdminCancelOrderRequestToJson(
  AdminCancelOrderRequest instance,
) => <String, dynamic>{'reason': instance.reason, 'version': instance.version};
