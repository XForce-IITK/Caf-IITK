import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../api/errors.dart';
import 'auth_form.dart';
import 'session.dart';

const instituteDomain = '@iitk.ac.in';
const minPasswordLength = 8;

/// Student self-registration (FR-1). Staff accounts are created by the
/// Administrator, so there is no role to choose here.
class RegisterScreen extends ConsumerStatefulWidget {
  const RegisterScreen({super.key});

  @override
  ConsumerState<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends ConsumerState<RegisterScreen> {
  final _form = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_busy || !_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref
          .read(sessionProvider.notifier)
          .register(_name.text.trim(), _email.text.trim(), _password.text);
    } on Object catch (error) {
      if (mounted) setState(() => _error = describeApiError(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String? _validateInstituteEmail(String? value) {
    final problem = validateEmail(value);
    if (problem != null) return problem;
    return value!.trim().toLowerCase().endsWith(instituteDomain)
        ? null
        : 'Use your $instituteDomain address';
  }

  String? _validatePassword(String? value) {
    return (value ?? '').length < minPasswordLength
        ? 'Use at least $minPasswordLength characters'
        : null;
  }

  @override
  Widget build(BuildContext context) {
    return AuthScaffold(
      title: 'Create a student account',
      child: Form(
        key: _form,
        child: AutofillGroup(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextFormField(
                key: const Key('name'),
                controller: _name,
                decoration: const InputDecoration(labelText: 'Name'),
                autofillHints: const [AutofillHints.name],
                textInputAction: TextInputAction.next,
                validator: (value) => validateRequired(value, 'name'),
              ),
              const SizedBox(height: 16),
              TextFormField(
                key: const Key('email'),
                controller: _email,
                decoration: const InputDecoration(
                  labelText: 'IITK email',
                  hintText: 'you$instituteDomain',
                ),
                keyboardType: TextInputType.emailAddress,
                autofillHints: const [AutofillHints.email],
                textInputAction: TextInputAction.next,
                validator: _validateInstituteEmail,
              ),
              const SizedBox(height: 16),
              TextFormField(
                key: const Key('password'),
                controller: _password,
                decoration: const InputDecoration(
                  labelText: 'Password',
                  helperText: 'At least $minPasswordLength characters',
                ),
                obscureText: true,
                autofillHints: const [AutofillHints.newPassword],
                validator: _validatePassword,
                onFieldSubmitted: (_) => _submit(),
              ),
              const SizedBox(height: 24),
              FormError(_error),
              FilledButton(
                key: const Key('submit'),
                onPressed: _busy ? null : _submit,
                child: Text(_busy ? 'Creating account…' : 'Create account'),
              ),
              const SizedBox(height: 8),
              TextButton(
                onPressed: _busy ? null : () => context.go('/login'),
                child: const Text('Already registered? Log in'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
