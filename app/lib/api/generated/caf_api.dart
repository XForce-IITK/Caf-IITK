// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:dio/dio.dart';

import 'clients/inventory_client.dart';
import 'clients/catalogue_client.dart';
import 'clients/slots_client.dart';
import 'clients/identity_client.dart';
import 'clients/ordering_client.dart';
import 'clients/pricing_client.dart';
import 'clients/ops_client.dart';

/// Caf@IITK API `v0.1.0`
class CafApi {
  CafApi(
    Dio dio, {
    String? baseUrl,
  })  : _dio = dio,
        _baseUrl = baseUrl;

  final Dio _dio;
  final String? _baseUrl;

  static String get version => '0.1.0';

  InventoryClient? _inventory;
  CatalogueClient? _catalogue;
  SlotsClient? _slots;
  IdentityClient? _identity;
  OrderingClient? _ordering;
  PricingClient? _pricing;
  OpsClient? _ops;

  InventoryClient get inventory => _inventory ??= InventoryClient(_dio, baseUrl: _baseUrl);

  CatalogueClient get catalogue => _catalogue ??= CatalogueClient(_dio, baseUrl: _baseUrl);

  SlotsClient get slots => _slots ??= SlotsClient(_dio, baseUrl: _baseUrl);

  IdentityClient get identity => _identity ??= IdentityClient(_dio, baseUrl: _baseUrl);

  OrderingClient get ordering => _ordering ??= OrderingClient(_dio, baseUrl: _baseUrl);

  PricingClient get pricing => _pricing ??= PricingClient(_dio, baseUrl: _baseUrl);

  OpsClient get ops => _ops ??= OpsClient(_dio, baseUrl: _baseUrl);
}
