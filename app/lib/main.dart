import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'router.dart';

void main() {
  runApp(const ProviderScope(child: CafApp()));
}

class CafApp extends ConsumerWidget {
  const CafApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return MaterialApp.router(
      title: 'Caf@IITK',
      theme: ThemeData(colorSchemeSeed: Colors.deepOrange, useMaterial3: true),
      routerConfig: ref.watch(routerProvider),
    );
  }
}
