// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:dio/dio.dart';
import 'package:retrofit/retrofit.dart';

import '../models/order_detail_out.dart';
import '../models/order_out.dart';
import '../models/place_order_request.dart';

part 'ordering_client.g.dart';

@RestApi()
abstract class OrderingClient {
  factory OrderingClient(Dio dio, {String? baseUrl}) = _OrderingClient;

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
  /// FR-40: the order's current status and every transition so far, oldest first.
  ///
  /// The client polls this every P-POLL while the order is not finished. Another.
  /// Student's order answers 404 and is logged as a security event (FR-7).
  @GET('/api/v1/orders/{order_id}')
  Future<OrderDetailOut> getOrder({@Path('order_id') required String orderId});
}
