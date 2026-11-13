import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/session.dart';
import '../brand.dart';
import '../theme.dart';

/// The frame every role's dashboard shares: its title and a log-out action.
class DashboardScaffold extends ConsumerWidget {
  const DashboardScaffold({super.key, required this.title, required this.body});

  final String title;
  final Widget body;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            const BrandMark(size: 26, showName: false),
            const SizedBox(width: 12),
            Text(
              'Caf@IITK',
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w700,
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 10),
              child: Text(
                '/',
                style: theme.textTheme.titleMedium?.copyWith(
                  color: CafColors.faint,
                  fontWeight: FontWeight.w400,
                ),
              ),
            ),
            Flexible(
              child: Text(
                title,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.titleMedium?.copyWith(
                  color: CafColors.muted,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            key: const Key('logout'),
            tooltip: 'Log out',
            icon: const Icon(Icons.logout, size: 20),
            onPressed: () => ref.read(sessionProvider.notifier).logout(),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: SafeArea(
        child: Align(
          alignment: Alignment.topCenter,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1200),
            child: SizedBox(width: double.infinity, child: body),
          ),
        ),
      ),
    );
  }
}
