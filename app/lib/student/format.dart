/// Money is integer paise throughout; this is the only place it becomes text.
String formatPaise(int paise) {
  final sign = paise < 0 ? '−' : '';
  final absolute = paise.abs();
  final rupees = absolute ~/ 100;
  final remainder = absolute % 100;
  final fraction = remainder == 0
      ? ''
      : '.${remainder.toString().padLeft(2, '0')}';
  return '$sign₹$rupees$fraction';
}

const _istOffset = Duration(hours: 5, minutes: 30);

/// The cafeteria runs on IST wall-clock time, whatever the browser's zone is.
String formatIstTime(DateTime moment) {
  final ist = moment.toUtc().add(_istOffset);
  String two(int value) => value.toString().padLeft(2, '0');
  return '${two(ist.hour)}:${two(ist.minute)}';
}

String formatSlot(DateTime startsAt, DateTime endsAt) {
  return '${formatIstTime(startsAt)} – ${formatIstTime(endsAt)}';
}
