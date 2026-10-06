// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:dio/dio.dart';
import 'package:retrofit/retrofit.dart';

import '../models/inventory_out.dart';
import '../models/inventory_set.dart';

part 'inventory_client.g.dart';

@RestApi()
abstract class InventoryClient {
  factory InventoryClient(Dio dio, {String? baseUrl}) = _InventoryClient;

  /// Set Inventory.
  ///
  /// FR-14 / US-11: set the prepared portions of an item for a service date (0-500).
  @PUT('/api/v1/admin/inventory/{service_date}/{item_id}')
  Future<InventoryOut> setInventory({
    @Path('service_date') required DateTime serviceDate,
    @Path('item_id') required String itemId,
    @Body() required InventorySet body,
  });
}
