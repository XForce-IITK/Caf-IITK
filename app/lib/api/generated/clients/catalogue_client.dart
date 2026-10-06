// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:dio/dio.dart';
import 'package:retrofit/retrofit.dart';

import '../models/item_create.dart';
import '../models/item_out.dart';
import '../models/menu_out.dart';

part 'catalogue_client.g.dart';

@RestApi()
abstract class CatalogueClient {
  factory CatalogueClient(Dio dio, {String? baseUrl}) = _CatalogueClient;

  /// Onboard Item.
  ///
  /// FR-8 / US-06: add a dish; it is ACTIVE immediately.
  @POST('/api/v1/admin/items')
  Future<ItemOut> onboardItem({@Body() required ItemCreate body});

  /// Browse Menu.
  ///
  /// FR-13 / US-10: the menu for a service date, with what is left of each item.
  ///
  /// [date] - Defaults to the current service date.
  @GET('/api/v1/menu')
  Future<MenuOut> browseMenu({@Query('date') DateTime? date});
}
