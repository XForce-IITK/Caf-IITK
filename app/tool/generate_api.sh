#!/usr/bin/env bash
# Regenerates the Dart API client from caf-api's OpenAPI schema (NFR-39).
# Run from anywhere; CI runs it too and fails if the committed files differ.
set -euo pipefail

app_dir="$(cd "$(dirname "$0")/.." && pwd)"
backend_dir="$app_dir/../backend"

python="${PYTHON:-}"
if [ -z "$python" ]; then
  if [ -x "$backend_dir/.venv/bin/python" ]; then
    python="$backend_dir/.venv/bin/python"
  else
    python=python3
  fi
fi

(cd "$backend_dir" && "$python" -m app.openapi_export "$app_dir/openapi.json")

cd "$app_dir"
rm -rf lib/api/generated
dart run swagger_parser
dart run build_runner build --delete-conflicting-outputs
# Formatted, so running `dart format` over the app leaves the client unchanged.
dart format lib/api/generated > /dev/null
