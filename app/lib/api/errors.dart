import 'package:dio/dio.dart';

/// A message fit to show the user for a failed API call. Uses the server's
/// `detail` when it is plain text, and never exposes anything else.
String describeApiError(Object error) {
  if (error is! DioException) return 'Something went wrong. Please try again.';
  final response = error.response;
  if (response == null) {
    return 'Could not reach the server. Check your connection and try again.';
  }
  final data = response.data;
  final detail = data is Map ? data['detail'] : null;
  if (detail is String && detail.isNotEmpty) return detail;
  if (response.statusCode == 422) {
    final message = _firstValidationMessage(detail);
    if (message != null) return message;
    return 'Some of the details entered are not valid.';
  }
  if (response.statusCode == 429) {
    return 'Too many attempts. Please wait a minute and try again.';
  }
  return 'Something went wrong. Please try again.';
}

/// FastAPI reports validation failures as a list of `{loc, msg}` entries.
String? _firstValidationMessage(Object? detail) {
  if (detail is! List || detail.isEmpty) return null;
  final first = detail.first;
  if (first is! Map) return null;
  final message = first['msg'];
  if (message is! String || message.isEmpty) return null;
  final location = first['loc'];
  final field = location is List && location.isNotEmpty ? location.last : null;
  final text = message.replaceFirst('Value error, ', '');
  return field is String ? '$field: $text' : text;
}
