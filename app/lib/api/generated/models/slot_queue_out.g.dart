// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'slot_queue_out.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

SlotQueueOut _$SlotQueueOutFromJson(Map<String, dynamic> json) => SlotQueueOut(
  endsAt: DateTime.parse(json['ends_at'] as String),
  itemTotals: (json['item_totals'] as List<dynamic>)
      .map((e) => QueueLineOut.fromJson(e as Map<String, dynamic>))
      .toList(),
  orders: (json['orders'] as List<dynamic>)
      .map((e) => QueueOrderOut.fromJson(e as Map<String, dynamic>))
      .toList(),
  proposalId: json['proposal_id'] as String?,
  slotId: json['slot_id'] as String,
  startsAt: DateTime.parse(json['starts_at'] as String),
  totalsOrder: TotalsOrder.fromJson(json['totals_order'] as String),
);

Map<String, dynamic> _$SlotQueueOutToJson(SlotQueueOut instance) =>
    <String, dynamic>{
      'ends_at': instance.endsAt.toIso8601String(),
      'item_totals': instance.itemTotals,
      'orders': instance.orders,
      'proposal_id': instance.proposalId,
      'slot_id': instance.slotId,
      'starts_at': instance.startsAt.toIso8601String(),
      'totals_order': instance.totalsOrder,
    };
