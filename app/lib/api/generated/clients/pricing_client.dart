// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:dio/dio.dart';
import 'package:retrofit/retrofit.dart';

import '../models/discount_rule_create.dart';
import '../models/discount_rule_out.dart';
import '../models/discount_rule_update.dart';
import '../models/quote_out.dart';
import '../models/quote_request.dart';

part 'pricing_client.g.dart';

@RestApi()
abstract class PricingClient {
  factory PricingClient(Dio dio, {String? baseUrl}) = _PricingClient;

  /// List Discount Rules.
  ///
  /// FR-22: every discount rule, active or not, by start time.
  @GET('/api/v1/admin/discount-rules')
  Future<List<DiscountRuleOut>> listDiscountRules();

  /// Create Discount Rule.
  ///
  /// FR-22 / US-17: add a time-of-day discount; it is active immediately.
  ///
  /// It applies to slots starting in [start_time, end_time). Rules may overlap; a.
  /// line gets only the highest percentage among the rules that cover it (FR-24).
  @POST('/api/v1/admin/discount-rules')
  Future<DiscountRuleOut> createDiscountRule({
    @Body() required DiscountRuleCreate body,
  });

  /// Update Discount Rule.
  ///
  /// FR-22: edit a rule, or deactivate it with `active: false`.
  ///
  /// Orders already placed keep their price snapshots; only later quotes see the change.
  @PATCH('/api/v1/admin/discount-rules/{rule_id}')
  Future<DiscountRuleOut> updateDiscountRule({
    @Path('rule_id') required String ruleId,
    @Body() required DiscountRuleUpdate body,
  });

  /// Create Quote.
  ///
  /// FR-25: the full FR-24 breakdown for a cart and slot. Reserves nothing.
  @POST('/api/v1/quotes')
  Future<QuoteOut> createQuote({@Body() required QuoteRequest body});
}
