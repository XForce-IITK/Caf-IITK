import 'package:caf_app/main.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('app starts on the home screen', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: CafApp()));
    await tester.pumpAndSettle();

    expect(find.text('Caf@IITK'), findsOneWidget);
    expect(find.text('Pre-order your meal and pickup slot.'), findsOneWidget);
  });
}
