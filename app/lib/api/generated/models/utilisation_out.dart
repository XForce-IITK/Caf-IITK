// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'item_utilisation_out.dart';
import 'slot_utilisation_out.dart';

part 'utilisation_out.g.dart';

/// FR-46: how full each slot and item is on a service date, and orders per state.
@JsonSerializable()
class UtilisationOut {
  const UtilisationOut({
    required this.asOf,
    required this.items,
    required this.orderCounts,
    required this.serviceDate,
    required this.slots,
  });

  factory UtilisationOut.fromJson(Map<String, Object?> json) =>
      _$UtilisationOutFromJson(json);

  @JsonKey(name: 'as_of')
  final DateTime asOf;
  final List<ItemUtilisationOut> items;
  @JsonKey(name: 'order_counts')
  final Map<String, int> orderCounts;
  @JsonKey(name: 'service_date')
  final DateTime serviceDate;
  final List<SlotUtilisationOut> slots;

  Map<String, Object?> toJson() => _$UtilisationOutToJson(this);
}
