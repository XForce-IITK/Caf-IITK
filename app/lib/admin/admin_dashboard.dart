import 'package:flutter/material.dart';

import '../dashboards/dashboard_scaffold.dart';
import 'agent_tab.dart';
import 'items_tab.dart';
import 'proposals_tab.dart';
import 'service_day_tab.dart';

/// The Administrator's screen (FR-63): proposals waiting for a decision, the
/// planning agent's runs and reports, items and portions, and the service day.
class AdminDashboard extends StatelessWidget {
  const AdminDashboard({super.key});

  static const _tabs = [
    (Key('tab-proposals'), 'Proposals', ProposalsTab()),
    (Key('tab-agent'), 'Agent runs', AgentTab()),
    (Key('tab-items'), 'Items & portions', ItemsTab()),
    (Key('tab-service-day'), 'Service window', ServiceDayTab()),
  ];

  @override
  Widget build(BuildContext context) {
    return DashboardScaffold(
      title: 'Administrator',
      body: DefaultTabController(
        length: _tabs.length,
        child: Column(
          children: [
            TabBar(
              isScrollable: true,
              tabs: [
                for (final (key, label, _) in _tabs) Tab(key: key, text: label),
              ],
            ),
            Expanded(
              child: TabBarView(
                children: [
                  for (final (_, _, page) in _tabs)
                    Align(
                      alignment: Alignment.topCenter,
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 900),
                        child: page,
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
