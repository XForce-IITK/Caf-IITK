// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:json_annotation/json_annotation.dart';

import 'quote_out.dart';

part 'modification_quote_out.g.dart';

/// UC-12 step 3: the new price and its difference from what was paid.
@JsonSerializable()
class ModificationQuoteOut {
  const ModificationQuoteOut({
    required this.differencePaise,
    required this.paidPaise,
    required this.quote,
  });

  factory ModificationQuoteOut.fromJson(Map<String, Object?> json) =>
      _$ModificationQuoteOutFromJson(json);

  @JsonKey(name: 'difference_paise')
  final int differencePaise;
  @JsonKey(name: 'paid_paise')
  final int paidPaise;
  final QuoteOut quote;

  Map<String, Object?> toJson() => _$ModificationQuoteOutToJson(this);
}
