import 'package:flutter/material.dart';

import 'dashboard_scaffold.dart';

/// The preparation queue is built under CAFIITK-179.
class KitchenDashboard extends StatelessWidget {
  const KitchenDashboard({super.key});

  @override
  Widget build(BuildContext context) {
    return const DashboardScaffold(
      title: 'Kitchen',
      body: Center(child: Text('The preparation queue will appear here.')),
    );
  }
}

/// Items, inventory, slots, agent runs and proposals are built under
/// CAFIITK-179.
class AdminDashboard extends StatelessWidget {
  const AdminDashboard({super.key});

  @override
  Widget build(BuildContext context) {
    return const DashboardScaffold(
      title: 'Administrator',
      body: Center(child: Text('Administration tools will appear here.')),
    );
  }
}
