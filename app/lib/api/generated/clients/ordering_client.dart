// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:dio/dio.dart';
import 'package:retrofit/retrofit.dart';

import '../models/admin_cancel_order_request.dart';
import '../models/cancel_order_request.dart';
import '../models/cancelled_order_out.dart';
import '../models/modification_quote_out.dart';
import '../models/modified_order_out.dart';
import '../models/modify_order_request.dart';
import '../models/order_detail_out.dart';
import '../models/order_out.dart';
import '../models/place_order_request.dart';
import '../models/quote_request.dart';

part 'ordering_client.g.dart';

@RestApi()
abstract class OrderingClient {
  factory OrderingClient(Dio dio, {String? baseUrl}) = _OrderingClient;

  /// Admin Cancel Order.
  ///
  /// FR-38: cancel an ACCEPTED, PREPARING or READY order with a mandatory reason and a.
  /// 100 % refund. The seat is always released; portions only from ACCEPTED (T6, T7, T9).
  ///
  /// `version` is the order version the Administrator saw. A repeat with the same key.
  /// returns the same result; there is never a second refund.
  @POST('/api/v1/admin/orders/{order_id}/cancel')
  Future<CancelledOrderOut> adminCancelOrder({
    @Path('order_id') required String orderId,
    @Header('Idempotency-Key') required String idempotencyKey,
    @Body() required AdminCancelOrderRequest body,
  });

  /// List My Orders.
  ///
  /// FR-28: the caller's own orders, newest first, each with its latest price.
  ///
  /// Open one with GET /orders/{order_id} for every snapshot version and refund.
  @GET('/api/v1/orders')
  Future<List<OrderOut>> listMyOrders({@Query('limit') int? limit = 50});

  /// Place Order.
  ///
  /// FR-30, FR-33: reserve the portions and a seat, then take payment.
  ///
  /// 201 with the order in ACCEPTED, or in PAYMENT_FAILED (holds returned) when the.
  /// payment is declined or times out. A repeat with the same key returns the same order.
  @POST('/api/v1/orders')
  Future<OrderOut> placeOrder({
    @Header('Idempotency-Key') required String idempotencyKey,
    @Body() required PlaceOrderRequest body,
  });

  /// Get Order.
  ///
  /// FR-40, FR-28: the order's current status and every transition, price snapshot.
  /// version and refund so far, oldest first.
  ///
  /// The client polls this every P-POLL while the order is not finished. Another.
  /// Student's order answers 404 and is logged as a security event (FR-7).
  @GET('/api/v1/orders/{order_id}')
  Future<OrderDetailOut> getOrder({@Path('order_id') required String orderId});

  /// Modify Order.
  ///
  /// FR-35, FR-36: replace an ACCEPTED order's items and/or slot before slot start -.
  /// P-CUTOFF, atomically. The order is re-priced as snapshot v(n+1); a higher price is.
  /// charged for the difference, a lower one refunded exactly once (FR-39).
  ///
  /// `lines` is the complete new cart. A repeat with the same key returns the same result.
  @PATCH('/api/v1/orders/{order_id}')
  Future<ModifiedOrderOut> modifyOrder({
    @Path('order_id') required String orderId,
    @Header('Idempotency-Key') required String idempotencyKey,
    @Body() required ModifyOrderRequest body,
  });

  /// Cancel Order.
  ///
  /// FR-37, FR-39: cancel from ACCEPTED (100 % refund, seat and portions restored) or.
  /// PREPARING (P-LATE_REFUND_PCT refund, seat restored) before slot start - P-CUTOFF.
  ///
  /// `version` is the order version the Student confirmed. A repeat with the same key.
  /// returns the same result; there is never a second refund.
  @POST('/api/v1/orders/{order_id}/cancel')
  Future<CancelledOrderOut> cancelOrder({
    @Path('order_id') required String orderId,
    @Header('Idempotency-Key') required String idempotencyKey,
    @Body() required CancelOrderRequest body,
  });

  /// Quote Order Modification.
  ///
  /// UC-12 step 3: what the order would cost with this cart and slot, and the.
  /// difference from what was paid. Read-only; nothing is reserved.
  @POST('/api/v1/orders/{order_id}/quote')
  Future<ModificationQuoteOut> quoteOrderModification({
    @Path('order_id') required String orderId,
    @Body() required QuoteRequest body,
  });
}
