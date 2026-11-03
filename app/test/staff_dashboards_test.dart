import 'package:caf_app/api/api.dart';
import 'package:caf_app/auth/session.dart';
import 'package:caf_app/dashboards/common.dart';
import 'package:caf_app/main.dart';
import 'package:caf_app/student/format.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_server.dart';

// P-POLL as the app defines it (pollIntervalProvider).
const _poll = Duration(seconds: 10);
const queueUrl = '/api/v1/kitchen/queue';
const proposalsUrl = '/api/v1/admin/proposals';
const runsUrl = '/api/v1/admin/agent/runs';

Map<String, Object?> _line(String id, String name, int qty) => {
  'item_id': id,
  'name': name,
  'qty': qty,
};

Map<String, Object?> _queueSlot(
  String id,
  String start,
  String end, {
  String totalsOrder = 'COUNT',
  List<Map<String, Object?>> orders = const [],
  List<Map<String, Object?>> totals = const [],
}) {
  return {
    'slot_id': id,
    'starts_at': start,
    'ends_at': end,
    'orders': orders,
    'item_totals': totals,
    'totals_order': totalsOrder,
    'proposal_id': totalsOrder == 'PREP_PRIORITY' ? 'p9' : null,
  };
}

Map<String, Object?> _queueOrder(String id, String status, String at) => {
  'id': id,
  'status': status,
  'confirmed_at': at,
  'lines': [_line('thali', 'Thali', 2)],
};

Map<String, Object?> _menuItem(String id, String name, {String? reason}) => {
  'id': id,
  'name': name,
  'description': '',
  'category': 'MEAL',
  'price_paise': 8000,
  'available_portions': 12,
  'orderable': reason == null,
  'not_orderable_reason': reason,
};

Map<String, Object?> _proposal(
  String id,
  String type,
  Object payload, {
  String status = 'PENDING',
  String? slotId,
  String? reason,
}) {
  return {
    'id': id,
    'type': type,
    'target_date': '2026-10-06',
    'target_slot_id': slotId,
    'payload': payload,
    'rationale': 'Forecast shows a stock-out by 13:00',
    'source': 'LLM',
    'status': status,
    'expires_at': '2026-10-06T06:30:00Z',
    'run_id': 'r1',
    'created_at': '2026-10-06T04:00:00Z',
    'decided_at': null,
    'decision_reason': reason,
  };
}

Map<String, Object?> _run(String id, String status, {String? source}) => {
  'id': id,
  'trigger': 'ON_DEMAND',
  'status': status,
  'source': source,
  'started_at': '2026-10-06T04:00:00Z',
  'finished_at': status == 'SUCCEEDED' ? '2026-10-06T04:00:20Z' : null,
};

/// caf-api as the staff dashboards see it. Tests replace a handler to script
/// a scenario; anything not scripted answers 404.
class _Cafe {
  _Cafe(this.role);

  final String role;
  final routes = <String, Reply Function(Seen request)>{};

  late final server = FakeServer((r) {
    if (r.path == loginUrl) return Reply(200, tokens(role));
    final handler = routes[r.path];
    if (handler != null) return handler(r);
    for (final entry in routes.entries) {
      if (entry.key.endsWith('*') &&
          r.path.startsWith(entry.key.substring(0, entry.key.length - 1))) {
        return entry.value(r);
      }
    }
    return const Reply(404, {'detail': 'Not found'});
  });

  Future<void> open(WidgetTester tester) async {
    tester.view.physicalSize = const Size(1000, 2400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final container = containerFor(server);
    await tester.runAsync(
      () =>
          container.read(sessionProvider.notifier).login('a@iitk.ac.in', 'pw'),
    );
    await tester.pumpWidget(
      UncontrolledProviderScope(container: container, child: const CafApp()),
    );
    await tester.pumpAndSettle();
  }
}

Future<void> _tap(WidgetTester tester, String key) async {
  final finder = find.byKey(Key(key));
  await tester.ensureVisible(finder);
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

String _text(WidgetTester tester, String key) {
  return switch (tester.widget(find.byKey(Key(key)))) {
    Text(:final data) => data!,
    FormMessage(:final text) => text,
    final other => throw StateError('no text in $other'),
  };
}

Future<void> _openTab(WidgetTester tester, String key) => _tap(tester, key);

void main() {
  group('Kitchen', () {
    late _Cafe cafe;
    late List<Map<String, Object?>> slots;
    var earlier = <Map<String, Object?>>[];
    Map<String, Object?> queueBody() => {
      'slots': slots,
      'earlier_slots': earlier,
    };

    setUp(() {
      cafe = _Cafe('KITCHEN');
      earlier = [];
      slots = [
        _queueSlot(
          's1',
          '2026-10-06T06:30:00Z',
          '2026-10-06T06:45:00Z',
          orders: [
            _queueOrder('order-aaaaaa', 'PREPARING', '2026-10-06T03:40:00Z'),
            _queueOrder('order-bbbbbb', 'READY', '2026-10-06T04:10:00Z'),
          ],
          totals: [_line('thali', 'Thali', 2)],
        ),
        _queueSlot(
          's2',
          '2026-10-06T06:45:00Z',
          '2026-10-06T07:00:00Z',
          totalsOrder: 'PREP_PRIORITY',
          totals: [_line('dosa', 'Dosa', 1), _line('thali', 'Thali', 3)],
        ),
      ];
      cafe.routes[queueUrl] = (_) => Reply(200, queueBody());
    });

    testWidgets('TC-US33: the queue shows the current and next slot, their '
        'orders and what to prepare', (tester) async {
      await cafe.open(tester);

      expect(find.textContaining('Current slot · 12:00 – 12:15'), findsOne);
      expect(find.textContaining('Next slot · 12:15 – 12:30'), findsOne);
      expect(_text(tester, 'total-s1-thali'), '1. Thali × 2');
      expect(_text(tester, 'totals-order-s1'), 'Most portions first');
      expect(
        _text(tester, 'totals-order-s2'),
        'In the order the Administrator approved',
      );
      expect(_text(tester, 'total-s2-dosa'), '1. Dosa × 1');
      expect(_text(tester, 'total-s2-thali'), '2. Thali × 3');
      final orders = find.descendant(
        of: find.byKey(const Key('queue-slot-s1')),
        matching: find.byType(ListTile),
      );
      expect(orders, findsNWidgets(2));
      expect(find.text('Preparing'), findsOne);
      expect(find.text('Ready'), findsOne);
      expect(find.textContaining('…aaaaaa · confirmed 09:10'), findsOne);
    });

    testWidgets('the queue refreshes every P-POLL and keeps the last one if '
        'a refresh fails', (tester) async {
      await cafe.open(tester);
      expect(cafe.server.to(queueUrl), hasLength(1));

      slots = [slots.last];
      await tester.pump(_poll);
      await tester.pumpAndSettle();
      expect(cafe.server.to(queueUrl), hasLength(2));
      expect(find.textContaining('Current slot · 12:15'), findsOne);

      cafe.routes[queueUrl] = (_) => const Reply(503);
      await tester.pump(_poll);
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('queue-stale')), findsOne);
      expect(find.textContaining('Current slot · 12:15'), findsOne);

      cafe.routes[queueUrl] = (_) =>
          const Reply(200, {'slots': [], 'earlier_slots': []});
      await tester.pump(_poll);
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('queue-empty')), findsOne);
      expect(find.byKey(const Key('queue-stale')), findsNothing);
    });

    testWidgets('a queue that cannot be loaded offers a retry', (tester) async {
      cafe.routes[queueUrl] = (_) => const Reply(500);
      await cafe.open(tester);
      expect(find.text('Try again'), findsOne);

      cafe.routes[queueUrl] = (_) => Reply(200, queueBody());
      await tester.tap(find.text('Try again'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Current slot'), findsOne);
    });
  });

  group('Kitchen transitions', () {
    late _Cafe cafe;
    late Map<String, Object?> queue;
    const transitionsUrl = '/api/v1/kitchen/orders';

    Map<String, Object?> slotWith(String id, String status, {String? end}) =>
        _queueSlot(
          'slot-$id',
          '2026-10-06T06:30:00Z',
          end ?? '2026-10-06T06:45:00Z',
          orders: [_queueOrder(id, status, '2026-10-06T03:40:00Z')],
        );

    setUp(() {
      cafe = _Cafe('KITCHEN');
      queue = {
        'slots': [slotWith('o-acc', 'ACCEPTED'), slotWith('o-ready', 'READY')],
        'earlier_slots': [slotWith('o-late', 'READY')],
      };
      cafe.routes[queueUrl] = (_) => Reply(200, queue);
    });

    testWidgets('TC-US34-AC1: each order offers only the moves its state '
        'allows', (tester) async {
      queue = {
        'slots': [
          slotWith('o-acc', 'ACCEPTED'),
          slotWith('o-prep', 'PREPARING'),
          slotWith('o-ready', 'READY'),
        ],
        'earlier_slots': [slotWith('o-late', 'READY')],
      };
      await cafe.open(tester);

      expect(find.byKey(const Key('START-o-acc')), findsOne);
      expect(find.byKey(const Key('READY-o-prep')), findsOne);
      expect(find.byKey(const Key('PICKED_UP-o-ready')), findsOne);
      // No-show only once the slot is over.
      expect(find.byKey(const Key('NO_SHOW-o-ready')), findsNothing);
      expect(find.textContaining('Ended · awaiting pickup'), findsOne);
      expect(find.byKey(const Key('NO_SHOW-o-late')), findsOne);
      expect(find.byKey(const Key('PICKED_UP-o-late')), findsOne);
    });

    testWidgets('starting an order sends the action and refreshes the queue', (
      tester,
    ) async {
      cafe.routes['$transitionsUrl/o-acc/transitions'] = (_) {
        queue = {
          'slots': [slotWith('o-acc', 'PREPARING')],
          'earlier_slots': [],
        };
        return const Reply(200, {
          'id': 'o-acc',
          'status': 'PREPARING',
          'slot_id': 'slot-o-acc',
          'version': 3,
        });
      };
      await cafe.open(tester);
      final loads = cafe.server.to(queueUrl).length;

      await _tap(tester, 'START-o-acc');

      final sent = cafe.server.to('$transitionsUrl/o-acc/transitions').single;
      expect(sent.method, 'POST');
      expect(sent.data, {'action': 'START'});
      expect(cafe.server.to(queueUrl).length, loads + 1);
      expect(find.byKey(const Key('READY-o-acc')), findsOne);
      expect(find.text('Preparing'), findsOne);
    });

    testWidgets('a no-show before the grace period says from when it is '
        'allowed', (tester) async {
      cafe.routes['$transitionsUrl/o-late/transitions'] = (_) =>
          const Reply(409, {
            'detail': {
              'message': 'too early for a no-show',
              'status': 'READY',
              'allowed_from': '2026-10-06T07:00:00Z',
            },
          });
      await cafe.open(tester);

      await _tap(tester, 'NO_SHOW-o-late');

      expect(
        _text(tester, 'order-error-o-late'),
        'Too early for a no-show: allowed from 12:30.',
      );
    });

    testWidgets('a move someone else already made is refused and the queue '
        'shows the real state', (tester) async {
      cafe.routes['$transitionsUrl/o-acc/transitions'] = (_) {
        queue = {
          'slots': [slotWith('o-acc', 'PREPARING')],
          'earlier_slots': [],
        };
        return const Reply(409, {
          'detail': {
            'message': 'cannot START an order that is PREPARING',
            'status': 'PREPARING',
          },
        });
      };
      await cafe.open(tester);

      await _tap(tester, 'START-o-acc');

      expect(
        _text(tester, 'order-error-o-acc'),
        'Not changed: the order is already PREPARING.',
      );
      expect(find.byKey(const Key('READY-o-acc')), findsOne);
    });

    testWidgets('a move the server cannot be reached for says so', (
      tester,
    ) async {
      cafe.routes['$transitionsUrl/o-ready/transitions'] = (r) =>
          throw networkFailure(r);
      await cafe.open(tester);

      await _tap(tester, 'PICKED_UP-o-ready');

      expect(_text(tester, 'order-error-o-ready'), contains('Could not reach'));
    });
  });

  group('Administrator', () {
    late _Cafe cafe;
    late List<Map<String, Object?>> pending;

    setUp(() {
      cafe = _Cafe('ADMIN');
      pending = [
        _proposal('p1', 'REPLENISH', {
          'lines': [
            {'item_id': 'thali', 'additional_portions': 40},
          ],
        }),
        _proposal('p2', 'PREP_PRIORITY', {
          'item_ids': ['dosa', 'thali'],
        }, slotId: 's2'),
        _proposal('p3', 'DISABLE', {'item_id': 'dosa', 'reason': 'No batter'}),
      ];
      cafe.routes[proposalsUrl] = (_) => Reply(200, pending);
      cafe.routes[menuUrl] = (_) => Reply(200, {
        'service_date': '2026-10-06',
        'items': [
          _menuItem('thali', 'Thali'),
          _menuItem('dosa', 'Dosa', reason: 'UNAVAILABLE'),
        ],
      });
      cafe.routes[slotsUrl] = (_) => const Reply(200, {
        'service_date': '2026-10-06',
        'slots': [
          {
            'id': 's2',
            'starts_at': '2026-10-06T06:45:00Z',
            'ends_at': '2026-10-06T07:00:00Z',
            'remaining_seats': 20,
            'bookable': true,
            'not_bookable_reason': null,
          },
        ],
      });
      cafe.routes[runsUrl] = (_) =>
          Reply(200, [_run('r1', 'SUCCEEDED', source: 'LLM')]);
    });

    testWidgets('UC-25: pending proposals show what they would change with '
        'item and slot names', (tester) async {
      await cafe.open(tester);

      expect(
        _text(tester, 'proposal-content-p1'),
        'Add portions for 06/10: Thali +40',
      );
      expect(
        _text(tester, 'proposal-content-p2'),
        'Prepare in this order for the 12:15 – 12:30 slot: 1. Dosa  2. Thali',
      );
      expect(
        _text(tester, 'proposal-content-p3'),
        'Mark Dosa unavailable for the rest of 06/10. Reason: No batter',
      );
      expect(find.textContaining('Why: Forecast shows'), findsNWidgets(3));
    });

    testWidgets('TC-US40-AC1: approving applies the proposal and refreshes '
        'the list', (tester) async {
      cafe.routes['$proposalsUrl/p1/approve'] = (_) {
        pending = pending.sublist(1);
        return Reply(200, _proposal('p1', 'REPLENISH', {}, status: 'APPROVED'));
      };
      await cafe.open(tester);

      await _tap(tester, 'approve-p1');

      expect(cafe.server.to('$proposalsUrl/p1/approve'), hasLength(1));
      expect(
        _text(tester, 'last-decision'),
        'Approved and applied: replenish stock.',
      );
      expect(find.byKey(const Key('proposal-p1')), findsNothing);
      expect(find.byKey(const Key('proposal-p2')), findsOne);
    });

    testWidgets('TC-US40-AC2: rejecting needs a reason', (tester) async {
      cafe.routes['$proposalsUrl/p3/reject'] = (_) {
        pending = pending.sublist(0, 2);
        return Reply(200, _proposal('p3', 'DISABLE', {}, status: 'REJECTED'));
      };
      await cafe.open(tester);

      await _tap(tester, 'reject-p3');
      await _tap(tester, 'confirm-reject');
      expect(find.text('A reason is required'), findsOne);
      expect(cafe.server.to('$proposalsUrl/p3/reject'), isEmpty);

      await tester.enterText(
        find.byKey(const Key('reject-reason')),
        '  Batter is fine today ',
      );
      await _tap(tester, 'confirm-reject');

      expect(cafe.server.to('$proposalsUrl/p3/reject').single.data, {
        'reason': 'Batter is fine today',
      });
      expect(_text(tester, 'last-decision'), 'Rejected: disable an item.');
      expect(find.byKey(const Key('proposal-p3')), findsNothing);
    });

    testWidgets('cancelling the reject dialog sends nothing', (tester) async {
      await cafe.open(tester);

      await _tap(tester, 'reject-p3');
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();

      expect(cafe.server.to('$proposalsUrl/p3/reject'), isEmpty);
      expect(find.byKey(const Key('last-decision')), findsNothing);
    });

    for (final (status, expected) in [
      (
        'INVALIDATED',
        'Not applied: it no longer fits the current state. Items no longer '
            'on the menu: thali',
      ),
      ('EXPIRED', 'Not applied: the proposal expired before it was approved.'),
      ('APPROVED', 'Not applied: the proposal was already decided (APPROVED).'),
    ]) {
      testWidgets('TC-US40-AC3/AC4: a 409 $status says why nothing was '
          'applied', (tester) async {
        cafe.routes['$proposalsUrl/p1/approve'] = (_) => Reply(409, {
          'detail': {
            'message': 'Not applied',
            'proposal': _proposal(
              'p1',
              'REPLENISH',
              {},
              status: status,
              reason: 'Items no longer on the menu: thali',
            ),
          },
        });
        await cafe.open(tester);

        await _tap(tester, 'approve-p1');

        expect(_text(tester, 'last-decision'), expected);
      });
    }

    testWidgets('a decision the server cannot be reached for says so', (
      tester,
    ) async {
      cafe.routes['$proposalsUrl/p1/approve'] = (r) => throw networkFailure(r);
      await cafe.open(tester);

      await _tap(tester, 'approve-p1');

      expect(_text(tester, 'last-decision'), contains('Could not reach'));
    });

    testWidgets('no pending proposals points to the agent', (tester) async {
      pending = [];
      await cafe.open(tester);
      expect(find.byKey(const Key('no-proposals')), findsOne);
    });

    testWidgets('FR-50: a run started here is followed until it finishes, '
        'then its proposals are listed', (tester) async {
      var runs = [_run('r1', 'SUCCEEDED', source: 'LLM')];
      cafe.routes[runsUrl] = (r) {
        if (r.method == 'POST') {
          runs = [_run('r2', 'QUEUED'), ...runs];
          return Reply(202, runs.first);
        }
        return Reply(200, runs);
      };
      await cafe.open(tester);
      await _openTab(tester, 'tab-agent');

      await _tap(tester, 'trigger-run');

      expect(_text(tester, 'run-status-r2'), 'Queued');
      expect(find.text('A run is in progress…'), findsOne);
      final proposalLoads = cafe.server.to(proposalsUrl).length;

      runs = [_run('r2', 'SUCCEEDED', source: 'HEURISTIC'), runs.last];
      await tester.pump(_poll);
      await tester.pumpAndSettle();

      expect(_text(tester, 'run-status-r2'), 'Finished · heuristic fallback');
      expect(find.text('Run planning now'), findsOne);
      // The finished run's proposals are fetched again for the Proposals tab.
      await _openTab(tester, 'tab-proposals');
      expect(cafe.server.to(proposalsUrl).length, greaterThan(proposalLoads));
    });

    testWidgets('TC-US39-AC2 client side: starting a run while one is in '
        'progress says so', (tester) async {
      cafe.routes[runsUrl] = (r) => r.method == 'POST'
          ? const Reply(409, {
              'detail': {'message': 'busy', 'running_run_id': 'r9'},
            })
          : Reply(200, [_run('r1', 'SUCCEEDED', source: 'LLM')]);
      await cafe.open(tester);
      await _openTab(tester, 'tab-agent');

      await _tap(tester, 'trigger-run');

      expect(
        _text(tester, 'trigger-message'),
        'A planning run is already in progress.',
      );
    });

    testWidgets('FR-63: a run shows its briefing, forecast and counts', (
      tester,
    ) async {
      cafe.routes['$runsUrl/r1'] = (_) => Reply(200, {
        ..._run('r1', 'SUCCEEDED', source: 'LLM'),
        'report': {
          'narrative': 'Thali will run out by 12:30.',
          'fallback_reason': null,
          'forecast': [
            {
              'item_id': 'thali',
              'item_name': 'Thali',
              'available': 10,
              'allocated': 4,
              'forecast_demand': 20,
              'stockout_slot_id': 's2',
              'stockout_slot_start': '2026-10-06T06:45:00Z',
              'risk': 'HIGH',
            },
          ],
        },
        'proposals': [],
        'tool_calls': [
          {
            'seq': 1,
            'tool': 'get_menu_config',
            'args': <String, Object?>{},
            'result_summary': 'ok',
            'latency_ms': 3,
            'outcome': 'OK',
          },
        ],
      });
      await cafe.open(tester);
      await _openTab(tester, 'tab-agent');

      await _tap(tester, 'run-r1');

      expect(find.text('Thali will run out by 12:30.'), findsOne);
      expect(find.text('HIGH'), findsOne);
      expect(find.text('12:15'), findsOne);
      expect(
        find.text('0 proposal(s) drafted · 1 tool call(s) logged'),
        findsOne,
      );
    });

    testWidgets('a failed run shows why', (tester) async {
      cafe.routes[runsUrl] = (_) => Reply(200, [_run('r3', 'FAILED')]);
      cafe.routes['$runsUrl/r3'] = (_) => Reply(200, {
        ..._run('r3', 'FAILED'),
        'report': {'error': 'internal error'},
        'proposals': [],
        'tool_calls': [],
      });
      await cafe.open(tester);
      await _openTab(tester, 'tab-agent');

      await _tap(tester, 'run-r3');

      expect(_text(tester, 'run-status-r3'), 'Failed');
      expect(find.text('The run failed: internal error'), findsOne);
    });

    testWidgets("TC-US11-AC1 client side, FR-14: setting an item's portions "
        'for today', (tester) async {
      final today = istToday();
      cafe.routes['/api/v1/admin/inventory/*'] = (_) => Reply(200, {
        'item_id': 'thali',
        'service_date': '2026-10-06',
        'total': 25,
        'allocated': 5,
        'available': 20,
      });
      await cafe.open(tester);
      await _openTab(tester, 'tab-items');

      await tester.enterText(find.byKey(const Key('portions-thali')), 'lots');
      await _tap(tester, 'set-portions-thali');
      expect(
        _text(tester, 'item-message-thali'),
        'Enter a number of portions from 0 to 500.',
      );

      await tester.enterText(find.byKey(const Key('portions-thali')), '25');
      await _tap(tester, 'set-portions-thali');

      final put = cafe.server.requests.singleWhere((r) => r.method == 'PUT');
      expect(put.path, startsWith('/api/v1/admin/inventory/'));
      expect(put.path, endsWith('/thali'));
      expect(Uri.decodeComponent(put.path), contains('$today'.split(' ')[0]));
      expect(put.data, {'total': 25});
      expect(
        _text(tester, 'item-message-thali'),
        'Portions set to 25 (20 left).',
      );
    });

    testWidgets('setting portions below those already ordered shows the '
        "server's reason", (tester) async {
      cafe.routes['/api/v1/admin/inventory/*'] = (_) => const Reply(409, {
        'detail': 'Total is below the 5 portions already ordered',
      });
      await cafe.open(tester);
      await _openTab(tester, 'tab-items');

      await tester.enterText(find.byKey(const Key('portions-thali')), '2');
      await _tap(tester, 'set-portions-thali');

      expect(
        _text(tester, 'item-message-thali'),
        'Total is below the 5 portions already ordered',
      );
    });

    testWidgets('TC-US09-AC1/AC3 client side, FR-11: marking an item '
        'unavailable needs a reason, and an '
        'unavailable item can be made available again', (tester) async {
      Reply item(Seen _) => Reply(200, {
        'id': 'x',
        'name': 'x',
        'description': '',
        'category': 'MEAL',
        'price_paise': 8000,
        'status': 'ACTIVE',
        'unavailable': false,
        'unavailable_reason': null,
      });
      cafe.routes['/api/v1/items/thali/flag'] = item;
      cafe.routes['/api/v1/items/dosa/flag'] = item;
      await cafe.open(tester);
      await _openTab(tester, 'tab-items');
      expect(_text(tester, 'item-status-dosa'), startsWith('Unavailable'));

      await _tap(tester, 'flag-thali');
      await _tap(tester, 'confirm-flag');
      expect(find.text('A reason is required'), findsOne);
      await tester.enterText(find.byKey(const Key('flag-reason')), 'Gas out');
      await _tap(tester, 'confirm-flag');

      final flag = cafe.server.to('/api/v1/items/thali/flag').single;
      expect(flag.method, 'POST');
      expect(flag.data, {'reason': 'Gas out'});
      expect(
        _text(tester, 'item-message-thali'),
        'Thali is marked unavailable.',
      );

      await _tap(tester, 'flag-dosa');
      expect(cafe.server.to('/api/v1/items/dosa/flag').single.method, 'DELETE');
      expect(_text(tester, 'item-message-dosa'), 'Dosa can be ordered again.');
    });

    testWidgets('TC-US06-AC1/AC3 client side, FR-8: adding an item sends its '
        'price in paise and refuses one under ₹1', (tester) async {
      cafe.routes['/api/v1/admin/items'] = (r) => Reply(201, {
        'id': 'new',
        'name': 'Vada Pav',
        'description': 'Spicy',
        'category': 'SNACK',
        'price_paise': 2550,
        'status': 'ACTIVE',
        'unavailable': false,
        'unavailable_reason': null,
      });
      await cafe.open(tester);
      await _openTab(tester, 'tab-items');

      await tester.enterText(
        find.byKey(const Key('new-item-name')),
        'Vada Pav',
      );
      await tester.enterText(find.byKey(const Key('new-item-price')), '0.50');
      await _tap(tester, 'add-item');
      expect(
        _text(tester, 'add-item-message'),
        'Enter a name and a price from ₹1 to ₹500.',
      );

      await tester.enterText(
        find.byKey(const Key('new-item-description')),
        'Spicy',
      );
      await tester.enterText(find.byKey(const Key('new-item-price')), '25.5');
      await _tap(tester, 'new-item-category');
      await tester.tap(find.text('Snack').last);
      await tester.pumpAndSettle();
      await _tap(tester, 'add-item');

      expect(cafe.server.to('/api/v1/admin/items').single.data, {
        'name': 'Vada Pav',
        'description': 'Spicy',
        'category': 'SNACK',
        'price_paise': 2550,
      });
      expect(
        _text(tester, 'add-item-message'),
        'Vada Pav added. Set its portions to put it on sale.',
      );
    });

    testWidgets('TC-US06-AC2 client side: adding an item with a taken name '
        'shows the server reason', (tester) async {
      cafe.routes['/api/v1/admin/items'] = (_) =>
          const Reply(409, {'detail': 'An item with this name exists'});
      await cafe.open(tester);
      await _openTab(tester, 'tab-items');

      await tester.enterText(find.byKey(const Key('new-item-name')), 'Thali');
      await tester.enterText(find.byKey(const Key('new-item-price')), '80');
      await _tap(tester, 'add-item');

      expect(
        _text(tester, 'add-item-message'),
        'An item with this name exists',
      );
    });

    group('staff accounts (US-03)', () {
      const usersUrl = '/api/v1/admin/users';
      Map<String, Object?> account(
        String id,
        String name,
        String role, {
        bool active = true,
      }) => {
        'id': id,
        'name': name,
        'email': '$id@caf.example',
        'role': role,
        'is_active': active,
      };
      late List<Map<String, Object?>> accounts;

      setUp(() {
        accounts = [
          account('admin', 'Asha', 'ADMIN'),
          account('ravi', 'Ravi', 'KITCHEN'),
          account('old', 'Old Cook', 'KITCHEN', active: false),
        ];
        cafe.routes[usersUrl] = (r) {
          if (r.method == 'GET') return Reply(200, accounts);
          final body = r.data! as Map<String, Object?>;
          final created = account(
            'new',
            body['name']! as String,
            body['role']! as String,
          );
          accounts = [...accounts, created];
          return Reply(201, created);
        };
        cafe.routes['$usersUrl/*'] = (r) {
          final id = r.path.split('/')[5];
          final active = r.path.endsWith('/reactivate');
          accounts = [
            for (final a in accounts)
              a['id'] == id ? {...a, 'is_active': active} : a,
          ];
          return Reply(200, accounts.firstWhere((a) => a['id'] == id));
        };
      });

      testWidgets('the tab lists staff accounts with their role and status', (
        tester,
      ) async {
        await cafe.open(tester);
        await _openTab(tester, 'tab-staff');

        expect(find.text('ravi@caf.example · Kitchen Staff'), findsOneWidget);
        expect(find.text('admin@caf.example · Administrator'), findsOneWidget);
        expect(
          find.text('old@caf.example · Kitchen Staff · Deactivated'),
          findsOneWidget,
        );
        expect(find.text('Reactivate'), findsOneWidget);
      });

      testWidgets('TC-US03-AC1: creating a Kitchen Staff account sends it and '
          'lists it', (tester) async {
        await cafe.open(tester);
        await _openTab(tester, 'tab-staff');

        await tester.enterText(
          find.byKey(const Key('new-staff-name')),
          'Meena',
        );
        await tester.enterText(
          find.byKey(const Key('new-staff-email')),
          'meena@caf.example',
        );
        await tester.enterText(
          find.byKey(const Key('new-staff-password')),
          'short',
        );
        await _tap(tester, 'add-staff');
        expect(
          _text(tester, 'add-staff-message'),
          'Enter a name, an email address and a password of at least 8 '
          'characters.',
        );
        expect(
          cafe.server.to(usersUrl).where((r) => r.method == 'POST'),
          isEmpty,
        );

        await tester.enterText(
          find.byKey(const Key('new-staff-password')),
          'kitchen-horse',
        );
        await _tap(tester, 'add-staff');

        final sent = cafe.server.to(usersUrl).where((r) => r.method == 'POST');
        expect(sent.single.data, {
          'name': 'Meena',
          'email': 'meena@caf.example',
          'password': 'kitchen-horse',
          'role': 'KITCHEN',
        });
        expect(
          _text(tester, 'add-staff-message'),
          'Meena can now log in as Kitchen Staff.',
        );
        expect(find.byKey(const Key('account-new')), findsOneWidget);
      });

      testWidgets('an Administrator account can be created too', (
        tester,
      ) async {
        await cafe.open(tester);
        await _openTab(tester, 'tab-staff');

        await tester.enterText(find.byKey(const Key('new-staff-name')), 'Dev');
        await tester.enterText(
          find.byKey(const Key('new-staff-email')),
          'dev@caf.example',
        );
        await tester.enterText(
          find.byKey(const Key('new-staff-password')),
          'admin-horse',
        );
        final segment = find.descendant(
          of: find.byKey(const Key('new-staff-role')),
          matching: find.text('Administrator'),
        );
        await tester.ensureVisible(segment);
        await tester.tap(segment);
        await tester.pumpAndSettle();
        await _tap(tester, 'add-staff');

        final sent = cafe.server.to(usersUrl).where((r) => r.method == 'POST');
        expect((sent.single.data! as Map)['role'], 'ADMIN');
      });

      testWidgets('TC-US03-AC2: deactivating asks first, then marks the '
          'account deactivated', (tester) async {
        await cafe.open(tester);
        await _openTab(tester, 'tab-staff');

        await _tap(tester, 'toggle-ravi');
        expect(find.text('Deactivate Ravi?'), findsOneWidget);
        await tester.tap(find.text('Cancel'));
        await tester.pumpAndSettle();
        expect(cafe.server.to('$usersUrl/ravi/deactivate'), isEmpty);

        await _tap(tester, 'toggle-ravi');
        await _tap(tester, 'confirm-deactivate');

        expect(cafe.server.to('$usersUrl/ravi/deactivate'), hasLength(1));
        expect(
          find.text('ravi@caf.example · Kitchen Staff · Deactivated'),
          findsOneWidget,
        );
      });

      testWidgets('reactivating needs no confirmation', (tester) async {
        await cafe.open(tester);
        await _openTab(tester, 'tab-staff');

        await _tap(tester, 'toggle-old');

        expect(cafe.server.to('$usersUrl/old/reactivate'), hasLength(1));
        expect(find.text('old@caf.example · Kitchen Staff'), findsOneWidget);
      });

      testWidgets("deactivating one's own account shows the server's reason", (
        tester,
      ) async {
        cafe.routes['$usersUrl/*'] = (_) => const Reply(409, {
          'detail': "You cannot change your own account's status",
        });
        await cafe.open(tester);
        await _openTab(tester, 'tab-staff');

        await _tap(tester, 'toggle-admin');
        await _tap(tester, 'confirm-deactivate');

        expect(
          _text(tester, 'account-message-admin'),
          "You cannot change your own account's status",
        );
      });

      testWidgets('a taken email shows the server reason', (tester) async {
        cafe.routes[usersUrl] = (r) => r.method == 'GET'
            ? Reply(200, accounts)
            : const Reply(409, {'detail': 'Email already registered'});
        await cafe.open(tester);
        await _openTab(tester, 'tab-staff');

        await tester.enterText(find.byKey(const Key('new-staff-name')), 'Ravi');
        await tester.enterText(
          find.byKey(const Key('new-staff-email')),
          'ravi@caf.example',
        );
        await tester.enterText(
          find.byKey(const Key('new-staff-password')),
          'kitchen-horse',
        );
        await _tap(tester, 'add-staff');

        expect(_text(tester, 'add-staff-message'), 'Email already registered');
      });
    });

    testWidgets("TC-US14-AC1 client side, FR-17: configuring tomorrow's "
        'service window', (tester) async {
      final tomorrow = istToday().add(const Duration(days: 1));
      cafe.routes['/api/v1/admin/service-days/*'] = (_) => const Reply(200, {
        'service_date': '2026-10-07',
        'window_start': '11:30:00',
        'window_end': '12:30:00',
        'slot_len_min': 20,
        'default_capacity': 25,
        'slots': [],
      });
      await cafe.open(tester);
      await _openTab(tester, 'tab-service-day');

      await tester.enterText(find.byKey(const Key('window-start')), '11.30');
      await _tap(tester, 'save-service-day');
      expect(
        _text(tester, 'service-day-message'),
        'Enter the window as HH:MM, for example 12:00.',
      );

      await tester.tap(find.text('Tomorrow'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byKey(const Key('window-start')), '11:30');
      await tester.enterText(find.byKey(const Key('window-end')), '12:30');
      await tester.enterText(find.byKey(const Key('slot-length')), 'x');
      await _tap(tester, 'save-service-day');
      expect(
        _text(tester, 'service-day-message'),
        'Slot length and seats must be whole numbers.',
      );

      await tester.enterText(find.byKey(const Key('slot-length')), '20');
      await tester.enterText(find.byKey(const Key('capacity')), '25');
      await _tap(tester, 'save-service-day');

      final put = cafe.server.requests.singleWhere((r) => r.method == 'PUT');
      expect(
        Uri.decodeComponent(put.path),
        contains('$tomorrow'.split(' ')[0]),
      );
      expect(put.data, {
        'window_start': '11:30',
        'window_end': '12:30',
        'slot_len_min': 20,
        'default_capacity': 25,
      });
      expect(
        _text(tester, 'service-day-message'),
        'Saved: 0 pickup slots of 20 minutes, 25 seats each.',
      );
    });

    testWidgets('TC-US14-AC2 client side: a slot length that does not divide '
        'the window shows the server reason', (tester) async {
      cafe.routes['/api/v1/admin/service-days/*'] = (_) => const Reply(422, {
        'detail': 'slot length 20 min does not divide the 150-minute window',
      });
      await cafe.open(tester);
      await _openTab(tester, 'tab-service-day');

      await tester.enterText(find.byKey(const Key('slot-length')), '20');
      await _tap(tester, 'save-service-day');

      expect(
        _text(tester, 'service-day-message'),
        'slot length 20 min does not divide the 150-minute window',
      );
    });

    testWidgets('TC-US15-AC2 client side: a window that would remove a slot '
        'with orders shows the server reason', (tester) async {
      cafe.routes['/api/v1/admin/service-days/*'] = (_) => const Reply(409, {
        'detail': 'the 12:00 slot has orders and would be removed',
      });
      await cafe.open(tester);
      await _openTab(tester, 'tab-service-day');

      await tester.enterText(find.byKey(const Key('window-start')), '12:30');
      await _tap(tester, 'save-service-day');

      expect(
        _text(tester, 'service-day-message'),
        'the 12:00 slot has orders and would be removed',
      );
    });

    testWidgets('the service window tab lists the date\'s slots', (
      tester,
    ) async {
      await cafe.open(tester);
      await _openTab(tester, 'tab-service-day');

      expect(find.byKey(const Key('admin-slot-s2')), findsOne);
      expect(_text(tester, 'admin-slot-s2'), '12:15 – 12:30 · 20 seats left');
    });

    group('monitoring the day (US-37)', () {
      const ordersUrl = '/api/v1/admin/orders';
      const utilisationUrl = '/api/v1/admin/utilisation';

      Map<String, Object?> adminOrder(
        String id,
        String slotId,
        String startsAt,
        String status,
        String student,
      ) => {
        'id': id,
        'status': status,
        'slot_id': slotId,
        'version': 1,
        'paid_paise': 8000,
        'subsidy_applied': false,
        'price': {
          'lines': [
            {
              'item_id': 'thali',
              'name': 'Thali',
              'unit_price_paise': 8000,
              'qty': 1,
              'line_base_paise': 8000,
              'rule_id': null,
              'discount_pct': 0,
              'line_discount_paise': 0,
              'line_total_paise': 8000,
            },
          ],
          'slot_id': slotId,
          'discounted_subtotal_paise': 8000,
          'subsidy_paise': 0,
          'rounding_adjustment_paise': 0,
          'payable_paise': 8000,
        },
        'created_at': '2026-10-06T03:40:00Z',
        'student_id': 'u-$student',
        'student_name': student,
        'student_email': '${student.toLowerCase()}@iitk.ac.in',
        'slot_starts_at': startsAt,
      };

      late List<Map<String, Object?>> orders;

      setUp(() {
        orders = [
          adminOrder('o1', 's1', '2026-10-06T06:30:00Z', 'ACCEPTED', 'Ravi'),
          adminOrder('o2', 's2', '2026-10-06T06:45:00Z', 'ACCEPTED', 'Asha'),
          adminOrder('o3', 's2', '2026-10-06T06:45:00Z', 'CANCELLED', 'Meera'),
        ];
        // Filters the way caf-api does, so the screen shows what it would.
        cafe.routes[ordersUrl] = (r) {
          // The query as it goes on the wire, as caf-api would parse it.
          final query = r.options.uri.queryParameters;
          final statuses = r.options.uri.queryParametersAll['status'] ?? [];
          return Reply(200, [
            for (final order in orders)
              if ((query['slot_id'] == null ||
                      order['slot_id'] == query['slot_id']) &&
                  (statuses.isEmpty || statuses.contains(order['status'])) &&
                  (query['student'] == null ||
                      (order['student_name'] as String).toLowerCase().contains(
                        (query['student'] as String).toLowerCase(),
                      )))
                order,
          ]);
        };
      });

      Future<void> choose(WidgetTester tester, String menu, String item) async {
        await _tap(tester, menu);
        await tester.tap(find.byKey(Key(item)).last);
        await tester.pumpAndSettle();
      }

      testWidgets('TC-US37-AC1: filtering by slot 12:15 and state ACCEPTED '
          'lists only matching orders', (tester) async {
        await cafe.open(tester);
        await _openTab(tester, 'tab-orders');
        expect(_text(tester, 'orders-count'), '3 orders');

        await choose(tester, 'filter-slot', 'filter-slot-s2');
        await choose(tester, 'filter-status', 'filter-status-ACCEPTED');

        final sent = cafe.server.to(ordersUrl).last.options.uri;
        expect(sent.queryParameters['slot_id'], 's2');
        expect(sent.queryParametersAll['status'], ['ACCEPTED']);
        expect(
          sent.queryParameters['date'],
          serviceDate(istToday()).toIso8601String(),
        );
        expect(_text(tester, 'orders-count'), '1 order');
        expect(find.byKey(const Key('admin-order-o2')), findsOne);
        expect(find.byKey(const Key('admin-order-o1')), findsNothing);
        expect(find.byKey(const Key('admin-order-o3')), findsNothing);
        expect(find.textContaining('12:15 · Asha'), findsOne);
        expect(find.textContaining('Thali × 1 · ₹80'), findsOne);
      });

      testWidgets('searching by Student sends the text; nothing matching '
          'says so', (tester) async {
        await cafe.open(tester);
        await _openTab(tester, 'tab-orders');

        await tester.enterText(
          find.byKey(const Key('filter-student')),
          ' rav ',
        );
        await _tap(tester, 'filter-student-search');
        expect(
          cafe.server.to(ordersUrl).last.options.queryParameters['student'],
          'rav',
        );
        expect(find.byKey(const Key('admin-order-o1')), findsOne);
        expect(_text(tester, 'orders-count'), '1 order');

        await tester.enterText(find.byKey(const Key('filter-student')), 'zed');
        await tester.testTextInput.receiveAction(TextInputAction.done);
        await tester.pumpAndSettle();
        expect(find.byKey(const Key('orders-empty')), findsOne);
      });

      Map<String, Object?> utilisation(int booked, int allocated) => {
        'service_date': '2026-10-06',
        'as_of': '2026-10-06T04:30:00Z',
        'slots': [
          {
            'slot_id': 's2',
            'starts_at': '2026-10-06T06:45:00Z',
            'ends_at': '2026-10-06T07:00:00Z',
            'booked': booked,
            'capacity': 30,
          },
        ],
        'items': [
          {
            'item_id': 'thali',
            'name': 'Thali',
            'allocated': allocated,
            'total': 40,
            'available': 40 - allocated,
          },
        ],
        'order_counts': {
          'PENDING_PAYMENT': 0,
          'ACCEPTED': booked,
          'PREPARING': 0,
          'READY': 0,
          'PICKED_UP': 0,
          'NO_SHOW': 0,
          'CANCELLED': 1,
          'PAYMENT_FAILED': 0,
        },
      };

      testWidgets('TC-US37-AC2: utilisation figures update within 30 s as '
          'bookings change', (tester) async {
        var figures = utilisation(12, 15);
        cafe.routes[utilisationUrl] = (_) => Reply(200, figures);
        await cafe.open(tester);
        await _openTab(tester, 'tab-utilisation');

        expect(find.textContaining('12/30 seats booked'), findsOne);
        expect(find.textContaining('15/40 allocated · 25 left'), findsOne);
        expect(_text(tester, 'utilisation-as-of'), startsWith('As of 10:00'));
        expect(find.text('Accepted: 12'), findsOne);
        expect(find.text('Cancelled: 1'), findsOne);

        figures = utilisation(13, 17);
        // P-POLL is 10 s, so the change shows well within 30 s.
        expect(_poll, lessThanOrEqualTo(const Duration(seconds: 30)));
        await tester.pump(_poll);
        await tester.pumpAndSettle();
        expect(cafe.server.to(utilisationUrl), hasLength(2));
        expect(find.textContaining('13/30 seats booked'), findsOne);
        expect(find.textContaining('17/40 allocated · 23 left'), findsOne);
        expect(find.text('Accepted: 13'), findsOne);
      });

      testWidgets('a failed utilisation refresh keeps the last figures', (
        tester,
      ) async {
        cafe.routes[utilisationUrl] = (_) => Reply(200, utilisation(12, 15));
        await cafe.open(tester);
        await _openTab(tester, 'tab-utilisation');

        cafe.routes[utilisationUrl] = (_) => const Reply(503);
        await tester.pump(_poll);
        await tester.pumpAndSettle();
        expect(find.byKey(const Key('utilisation-stale')), findsOne);
        expect(find.textContaining('12/30 seats booked'), findsOne);

        cafe.routes[utilisationUrl] = (_) => Reply(200, utilisation(14, 15));
        await tester.pump(_poll);
        await tester.pumpAndSettle();
        expect(find.byKey(const Key('utilisation-stale')), findsNothing);
        expect(find.textContaining('14/30 seats booked'), findsOne);
      });
    });
  });
}
