// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:dio/dio.dart';
import 'package:retrofit/retrofit.dart';

import '../models/kitchen_queue_out.dart';

part 'kitchen_client.g.dart';

@RestApi()
abstract class KitchenClient {
  factory KitchenClient(Dio dio, {String? baseUrl}) = _KitchenClient;

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
