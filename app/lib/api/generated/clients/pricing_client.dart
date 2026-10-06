// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:dio/dio.dart';
import 'package:retrofit/retrofit.dart';

import '../models/quote_out.dart';
import '../models/quote_request.dart';

part 'pricing_client.g.dart';

@RestApi()
abstract class PricingClient {
  factory PricingClient(Dio dio, {String? baseUrl}) = _PricingClient;

  /// Create Quote.
  ///
  /// FR-25: the full FR-24 breakdown for a cart and slot. Reserves nothing.
  @POST('/api/v1/quotes')
  Future<QuoteOut> createQuote({
    @Body() required QuoteRequest body,
  });
}
