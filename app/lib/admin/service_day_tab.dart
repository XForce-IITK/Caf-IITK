import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api.dart';
import '../api/errors.dart';
import '../dashboards/common.dart';
import '../student/format.dart';
import 'admin_state.dart';

/// FR-17, FR-18: set a service date's window, slot length and seats per slot;
/// the server cuts the window into pickup slots.
class ServiceDayTab extends ConsumerStatefulWidget {
  const ServiceDayTab({super.key});

  @override
  ConsumerState<ServiceDayTab> createState() => _ServiceDayTabState();
}

class _ServiceDayTabState extends ConsumerState<ServiceDayTab> {
  final _start = TextEditingController(text: '12:00');
  final _end = TextEditingController(text: '14:30');
  final _slotLength = TextEditingController(text: '15');
  final _capacity = TextEditingController(text: '30');
  bool _tomorrow = false;
  bool _busy = false;
  String? _message;
  bool _failed = false;

  DateTime get _date {
    final today = istToday();
    return _tomorrow ? DateTime(today.year, today.month, today.day + 1) : today;
  }

  @override
  void dispose() {
    for (final controller in [_start, _end, _slotLength, _capacity]) {
      controller.dispose();
    }
    super.dispose();
  }

  static final _time = RegExp(r'^([01]\d|2[0-3]):[0-5]\d$');

  Future<void> _submit() async {
    final start = _start.text.trim();
    final end = _end.text.trim();
    final slotLength = int.tryParse(_slotLength.text.trim());
    final capacity = int.tryParse(_capacity.text.trim());
    if (!_time.hasMatch(start) || !_time.hasMatch(end)) {
      return _show(
        'Enter the window as HH:MM, for example 12:00.',
        failed: true,
      );
    }
    if (slotLength == null || capacity == null) {
      return _show(
        'Slot length and seats must be whole numbers.',
        failed: true,
      );
    }
    setState(() => _busy = true);
    try {
      final day = await ref
          .read(apiProvider)
          .slots
          .configureServiceDay(
            serviceDate: serviceDate(_date),
            body: ServiceDayConfig(
              windowStart: start,
              windowEnd: end,
              slotLenMin: slotLength,
              defaultCapacity: capacity,
            ),
          );
      ref.invalidate(adminSlotsProvider(_date));
      _show(
        'Saved: ${day.slots.length} pickup slots of ${day.slotLenMin} '
        'minutes, ${day.defaultCapacity} seats each.',
      );
    } on Object catch (error) {
      _show(describeApiError(error), failed: true);
    }
  }

  void _show(String message, {bool failed = false}) {
    if (!mounted) return;
    setState(() {
      _busy = false;
      _message = message;
      _failed = failed;
    });
  }

  Widget _field(String key, TextEditingController controller, String label) {
    return SizedBox(
      width: 140,
      child: TextField(
        key: Key(key),
        controller: controller,
        decoration: InputDecoration(labelText: label),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const SectionHeading('Service window'),
        SegmentedButton<bool>(
          key: const Key('service-date'),
          segments: const [
            ButtonSegment(value: false, label: Text('Today')),
            ButtonSegment(value: true, label: Text('Tomorrow')),
          ],
          selected: {_tomorrow},
          onSelectionChanged: (choice) => setState(() {
            _tomorrow = choice.single;
            _message = null;
          }),
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 16,
          children: [
            _field('window-start', _start, 'Opens (HH:MM)'),
            _field('window-end', _end, 'Closes (HH:MM)'),
            _field('slot-length', _slotLength, 'Slot length (min)'),
            _field('capacity', _capacity, 'Seats per slot'),
          ],
        ),
        const SizedBox(height: 8),
        FilledButton(
          key: const Key('save-service-day'),
          onPressed: _busy ? null : _submit,
          child: const Text('Save'),
        ),
        if (_message case final message?)
          FormMessage(
            message,
            key: const Key('service-day-message'),
            isError: _failed,
          ),
        const SizedBox(height: 24),
        SectionHeading('Pickup slots · ${_tomorrow ? 'tomorrow' : 'today'}'),
        Loaded(
          value: ref.watch(adminSlotsProvider(_date)),
          onRetry: () => ref.invalidate(adminSlotsProvider(_date)),
          builder: (list) => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (list.slots.isEmpty) const Text('No slots configured.'),
              for (final slot in list.slots)
                Text(
                  '${formatSlot(slot.startsAt, slot.endsAt)} · '
                  '${slot.remainingSeats} seats left',
                  key: Key('admin-slot-${slot.id}'),
                ),
            ],
          ),
        ),
      ],
    );
  }
}
