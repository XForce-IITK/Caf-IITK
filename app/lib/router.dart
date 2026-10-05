import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

/// App routes. Login and the role-based redirect to exactly one dashboard
/// (FR-5) are added under CAFIITK-177.
final routerProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    routes: [
      GoRoute(path: '/', builder: (context, state) => const HomeScreen()),
    ],
  );
});

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Caf@IITK')),
      body: const Center(child: Text('Pre-order your meal and pickup slot.')),
    );
  }
}
