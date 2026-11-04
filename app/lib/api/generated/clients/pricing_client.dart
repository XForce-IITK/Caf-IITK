// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:dio/dio.dart';
import 'package:retrofit/retrofit.dart';

import '../models/discount_rule_create.dart';
import '../models/discount_rule_out.dart';
import '../models/discount_rule_update.dart';
import '../models/eligibility_update.dart';
import '../models/quote_out.dart';
import '../models/quote_request.dart';
import '../models/student_out.dart';
import '../models/subsidy_settings.dart';

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

  /// List Students.
  ///
  /// FR-23: Students by name, to find the one to mark eligible.
  ///
  /// `search` matches part of the name or email, ignoring case; `eligible`.
  /// keeps only Students who are (or are not) subsidy-eligible.
  @GET('/api/v1/admin/students')
  Future<List<StudentOut>> listStudents({
    @Query('limit') int? limit = 50,
    @Query('search') String? search,
    @Query('eligible') bool? eligible,
  });

  /// Get Subsidy Settings.
  ///
  /// FR-23: the current P-SUBSIDY_AMT (in paise) and P-SUBSIDY_CAP_PCT.
  @GET('/api/v1/admin/subsidy')
  Future<SubsidySettings> getSubsidySettings();

  /// Set Subsidy Settings.
  ///
  /// FR-23: set both subsidy parameters. An amount of 0 turns the subsidy off.
  ///
  /// Only later quotes see the change; placed orders keep their price snapshots.
  @PUT('/api/v1/admin/subsidy')
  Future<SubsidySettings> setSubsidySettings({
    @Body() required SubsidySettings body,
  });

  /// Set Subsidy Eligibility.
  ///
  /// FR-23 / US-18: mark a Student subsidy-eligible, or not.
  ///
  /// Their next quote includes the subsidy if they have no subsidised order that.
  /// day yet (FR-24 step 4). Staff accounts are not Students, so they get 404.
  @PUT('/api/v1/admin/users/{user_id}/eligibility')
  Future<StudentOut> setSubsidyEligibility({
    @Path('user_id') required String userId,
    @Body() required EligibilityUpdate body,
  });

  /// Create Quote.
  ///
  /// FR-25: the full FR-24 breakdown for a cart and slot. Reserves nothing.
  @POST('/api/v1/quotes')
  Future<QuoteOut> createQuote({@Body() required QuoteRequest body});
}
