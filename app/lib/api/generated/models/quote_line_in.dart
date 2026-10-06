// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

part 'quote_line_in.g.dart';

@JsonSerializable()
class QuoteLineIn {
  const QuoteLineIn({
    required this.itemId,
    required this.qty,
  });
  
  factory QuoteLineIn.fromJson(Map<String, Object?> json) => _$QuoteLineInFromJson(json);
  
  @JsonKey(name: 'item_id')
  final String itemId;
  final int qty;

  Map<String, Object?> toJson() => _$QuoteLineInToJson(this);
}
