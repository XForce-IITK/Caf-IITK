// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'kitchen_queue_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

KitchenQueueOut _$KitchenQueueOutFromJson(Map<String, dynamic> json) =>
    KitchenQueueOut(
      slots: (json['slots'] as List<dynamic>)
          .map((e) => SlotQueueOut.fromJson(e as Map<String, dynamic>))
          .toList(),
    );

Map<String, dynamic> _$KitchenQueueOutToJson(KitchenQueueOut instance) =>
    <String, dynamic>{'slots': instance.slots};
