"""The OpenAPI export the Flutter client is generated from (NFR-39)."""

import json
from collections import Counter
from pathlib import Path

import pytest

from app.main import create_app
from app.openapi_export import export_openapi, main


def test_export_writes_the_published_schema(tmp_path: Path) -> None:
    target = tmp_path / "openapi.json"

    assert main([str(target)]) == 0

    assert json.loads(target.read_text()) == create_app().openapi()


def test_export_is_stable_and_sorted(tmp_path: Path) -> None:
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    export_openapi(first)
    export_openapi(second)

    text = first.read_text()
    assert text == second.read_text()
    assert text.endswith("\n")
    assert list(json.loads(text)) == sorted(json.loads(text))


def test_export_needs_exactly_one_path(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert "usage" in capsys.readouterr().err


def test_operation_ids_are_the_endpoint_names_and_unique() -> None:
    """The generated client names its methods after these, so a clash would drop one."""
    paths = create_app().openapi()["paths"]
    ids = [operation["operationId"] for path in paths.values() for operation in path.values()]

    assert "place_order" in ids
    assert [name for name, count in Counter(ids).items() if count > 1] == []
