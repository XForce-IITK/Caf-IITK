import 'package:caf_app/api/errors.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

DioException _failure(int status, Object? body) {
  final options = RequestOptions(path: '/x');
  return DioException.badResponse(
    statusCode: status,
    requestOptions: options,
    response: Response(requestOptions: options, statusCode: status, data: body),
  );
}

void main() {
  test('a plain-text detail from the server is shown as it is', () {
    expect(
      describeApiError(_failure(409, {'detail': 'Thali is sold out'})),
      'Thali is sold out',
    );
  });

  test('a validation failure names the field and drops the prefix', () {
    final error = _failure(422, {
      'detail': [
        {
          'loc': ['body', 'email'],
          'msg': 'Value error, must be an @iitk.ac.in address',
        },
      ],
    });

    expect(describeApiError(error), 'email: must be an @iitk.ac.in address');
  });

  test('a validation failure without a usable message is still explained', () {
    expect(
      describeApiError(_failure(422, {'detail': <Object>[]})),
      'Some of the details entered are not valid.',
    );
    expect(
      describeApiError(
        _failure(422, {
          'detail': [
            {'loc': <Object>[], 'msg': 'Field required'},
          ],
        }),
      ),
      'Field required',
    );
    expect(
      describeApiError(
        _failure(422, {
          'detail': ['unexpected'],
        }),
      ),
      'Some of the details entered are not valid.',
    );
  });

  test('rate limiting asks the user to wait', () {
    expect(describeApiError(_failure(429, null)), contains('Too many'));
  });

  test('a server error shows nothing internal', () {
    expect(
      describeApiError(_failure(500, '<html>Traceback ...</html>')),
      'Something went wrong. Please try again.',
    );
  });

  test('no response means the server could not be reached', () {
    final error = DioException.connectionError(
      requestOptions: RequestOptions(path: '/x'),
      reason: 'refused',
    );

    expect(describeApiError(error), contains('Could not reach the server'));
  });

  test('anything else gets the generic message', () {
    expect(
      describeApiError(StateError('boom')),
      'Something went wrong. Please try again.',
    );
  });
}
