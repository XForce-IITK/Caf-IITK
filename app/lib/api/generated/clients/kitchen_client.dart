// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:dio/dio.dart';
import 'package:retrofit/retrofit.dart';

import '../models/kitchen_order_out.dart';
import '../models/kitchen_queue_out.dart';
import '../models/transition_request.dart';

part 'kitchen_client.g.dart';

@RestApi()
abstract class KitchenClient {
  factory KitchenClient(Dio dio, {String? baseUrl}) = _KitchenClient;

  /// Transition Kitchen Order.
  ///
  /// FR-43: Start (T5), Mark Ready (T8), Mark Picked Up (T10) or Mark No-show (T11).
  ///
  /// Any other move is refused with 409 and changes nothing (FR-29). A no-show keeps.
  /// the portions and is not refunded. The order version is bumped, so a Student.
  /// acting on what they saw before gets 409.
  @POST('/api/v1/kitchen/orders/{order_id}/transitions')
  Future<KitchenOrderOut> transitionKitchenOrder({
    @Path('order_id') required String orderId,
    @Body() required TransitionRequest body,
  });

  /// Get Kitchen Queue.
  ///
  /// FR-42: ACCEPTED, PREPARING and READY orders of the current and next slot.
  ///
  /// Orders are sorted by slot start, then confirmation time. Each slot's item.
  /// totals follow its approved prep-priority proposal (FR-54) if there is one,.
  /// otherwise descending count. The kitchen screen polls this every P-POLL.
  @GET('/api/v1/kitchen/queue')
  Future<KitchenQueueOut> getKitchenQueue();
}
