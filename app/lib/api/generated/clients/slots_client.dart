// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, unused_import, invalid_annotation_target, unnecessary_import

import 'package:dio/dio.dart';
import 'package:retrofit/retrofit.dart';

import '../models/service_day_config.dart';
import '../models/service_day_out.dart';
import '../models/slot_capacity_change.dart';
import '../models/slot_list_out.dart';
import '../models/slot_out.dart';

part 'slots_client.g.dart';

@RestApi()
abstract class SlotsClient {
  factory SlotsClient(Dio dio, {String? baseUrl}) = _SlotsClient;

  /// Configure Service Day.
  ///
  /// FR-17 / US-14: configure a service date's window and generate its slots.
  ///
  /// Slots that orders reference are kept; FR-18 refuses a change that would remove one.
  @PUT('/api/v1/admin/service-days/{service_date}')
  Future<ServiceDayOut> configureServiceDay({
    @Path('service_date') required DateTime serviceDate,
    @Body() required ServiceDayConfig body,
  });

  /// Change Slot Capacity.
  ///
  /// FR-18 / US-15: change one slot's capacity without dropping booked students.
  @PATCH('/api/v1/admin/slots/{slot_id}')
  Future<SlotOut> changeSlotCapacity({
    @Path('slot_id') required String slotId,
    @Body() required SlotCapacityChange body,
  });

  /// Browse Slots.
  ///
  /// FR-19 / US-16: a service date's pickup slots with their remaining seats.
  ///
  /// [date] - Defaults to the current service date.
  @GET('/api/v1/slots')
  Future<SlotListOut> browseSlots({@Query('date') DateTime? date});
}
