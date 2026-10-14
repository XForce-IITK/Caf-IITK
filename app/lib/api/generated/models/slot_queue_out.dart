// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'queue_line_out.dart';
import 'queue_order_out.dart';
import 'totals_order.dart';

part 'slot_queue_out.g.dart';

@JsonSerializable()
class SlotQueueOut {
  const SlotQueueOut({
    required this.endsAt,
    required this.itemTotals,
    required this.orders,
    required this.proposalId,
    required this.slotId,
    required this.startsAt,
    required this.totalsOrder,
  });

  factory SlotQueueOut.fromJson(Map<String, Object?> json) =>
      _$SlotQueueOutFromJson(json);

  @JsonKey(name: 'ends_at')
  final DateTime endsAt;
  @JsonKey(name: 'item_totals')
  final List<QueueLineOut> itemTotals;
  final List<QueueOrderOut> orders;
  @JsonKey(name: 'proposal_id')
  final String? proposalId;
  @JsonKey(name: 'slot_id')
  final String slotId;
  @JsonKey(name: 'starts_at')
  final DateTime startsAt;
  @JsonKey(name: 'totals_order')
  final TotalsOrder totalsOrder;

  Map<String, Object?> toJson() => _$SlotQueueOutToJson(this);
}
