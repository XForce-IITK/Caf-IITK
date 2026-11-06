import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api.dart';
import '../api/errors.dart';
import '../dashboards/common.dart';

/// UC-03: every Kitchen Staff and Administrator account, active or not.
final staffAccountsProvider = FutureProvider.autoDispose<List<AccountOut>>(
  (ref) => ref.watch(apiProvider).identity.listStaffAccounts(),
  retry: (_, _) => null,
);

String roleLabel(Role role) => switch (role) {
  Role.kitchen => 'Kitchen Staff',
  Role.admin => 'Administrator',
  Role.student => 'Student',
  Role.$unknown => 'Unknown',
};

/// FR-2, FR-3: create staff accounts, and deactivate or reactivate them.
class StaffTab extends ConsumerWidget {
  const StaffTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const SectionHeading('Staff accounts'),
        Loaded(
          value: ref.watch(staffAccountsProvider),
          onRetry: () => ref.invalidate(staffAccountsProvider),
          builder: (accounts) => Column(
            children: [
              if (accounts.isEmpty) const Text('No staff accounts yet.'),
              for (final account in accounts)
                _AccountRow(account, key: Key('account-${account.id}')),
            ],
          ),
        ),
        const SizedBox(height: 24),
        const SectionHeading('Add a staff account'),
        const _CreateForm(),
      ],
    );
  }
}

class _AccountRow extends ConsumerStatefulWidget {
  const _AccountRow(this.account, {super.key});

  final AccountOut account;

  @override
  ConsumerState<_AccountRow> createState() => _AccountRowState();
}

class _AccountRowState extends ConsumerState<_AccountRow> {
  bool _busy = false;
  String? _message;

  AccountOut get _account => widget.account;

  Future<void> _toggle() async {
    final deactivating = _account.isActive;
    if (deactivating) {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text('Deactivate ${_account.name}?'),
          content: const Text(
            'They are logged out at once and cannot log in until the account '
            'is reactivated.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              key: const Key('confirm-deactivate'),
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Deactivate'),
            ),
          ],
        ),
      );
      if (confirmed != true) return;
    }
    setState(() => _busy = true);
    final identity = ref.read(apiProvider).identity;
    String? message;
    try {
      if (deactivating) {
        await identity.deactivateAccount(userId: _account.id);
      } else {
        await identity.reactivateAccount(userId: _account.id);
      }
      ref.invalidate(staffAccountsProvider);
    } on Object catch (error) {
      message = describeApiError(error);
    }
    if (mounted) {
      setState(() {
        _busy = false;
        _message = message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final active = _account.isActive;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(_account.name, style: theme.textTheme.titleMedium),
                      Text(
                        '${_account.email} · ${roleLabel(_account.role)}'
                        '${active ? '' : ' · Deactivated'}',
                        style: active
                            ? null
                            : TextStyle(color: theme.colorScheme.error),
                      ),
                    ],
                  ),
                ),
                OutlinedButton(
                  key: Key('toggle-${_account.id}'),
                  onPressed: _busy ? null : _toggle,
                  child: Text(active ? 'Deactivate' : 'Reactivate'),
                ),
              ],
            ),
            if (_message case final message?)
              FormMessage(
                message,
                key: Key('account-message-${_account.id}'),
                isError: true,
              ),
          ],
        ),
      ),
    );
  }
}

class _CreateForm extends ConsumerStatefulWidget {
  const _CreateForm();

  @override
  ConsumerState<_CreateForm> createState() => _CreateFormState();
}

class _CreateFormState extends ConsumerState<_CreateForm> {
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  Role _role = Role.kitchen;
  bool _busy = false;
  String? _message;
  bool _failed = false;

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final name = _name.text.trim();
    final email = _email.text.trim();
    if (name.isEmpty || !email.contains('@') || _password.text.length < 8) {
      setState(() {
        _message =
            'Enter a name, an email address and a password of at least 8 '
            'characters.';
        _failed = true;
      });
      return;
    }
    setState(() => _busy = true);
    try {
      final account = await ref
          .read(apiProvider)
          .identity
          .createStaffAccount(
            body: StaffCreate(
              name: name,
              email: email,
              password: _password.text,
              role: _role,
            ),
          );
      _name.clear();
      _email.clear();
      _password.clear();
      ref.invalidate(staffAccountsProvider);
      _message =
          '${account.name} can now log in as ${roleLabel(account.role)}.';
      _failed = false;
    } on Object catch (error) {
      _message = describeApiError(error);
      _failed = true;
    }
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TextField(
          key: const Key('new-staff-name'),
          controller: _name,
          maxLength: 100,
          decoration: const InputDecoration(labelText: 'Name'),
        ),
        TextField(
          key: const Key('new-staff-email'),
          controller: _email,
          maxLength: 254,
          keyboardType: TextInputType.emailAddress,
          decoration: const InputDecoration(labelText: 'Email'),
        ),
        TextField(
          key: const Key('new-staff-password'),
          controller: _password,
          obscureText: true,
          maxLength: 128,
          decoration: const InputDecoration(
            labelText: 'Initial password',
            helperText: 'At least 8 characters. Share it with them privately.',
          ),
        ),
        const SizedBox(height: 8),
        SegmentedButton<Role>(
          key: const Key('new-staff-role'),
          segments: const [
            ButtonSegment(value: Role.kitchen, label: Text('Kitchen Staff')),
            ButtonSegment(value: Role.admin, label: Text('Administrator')),
          ],
          selected: {_role},
          onSelectionChanged: (roles) => setState(() => _role = roles.single),
        ),
        const SizedBox(height: 8),
        FilledButton(
          key: const Key('add-staff'),
          onPressed: _busy ? null : _submit,
          child: const Text('Create account'),
        ),
        if (_message case final message?)
          FormMessage(
            message,
            key: const Key('add-staff-message'),
            isError: _failed,
          ),
      ],
    );
  }
}
