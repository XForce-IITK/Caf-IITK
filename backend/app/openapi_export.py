"""Write caf-api's OpenAPI schema to a file: `python -m app.openapi_export <path>`.

The Flutter API client is generated from this file, and CI regenerates both and
fails on any difference (NFR-39). Keys are sorted so the output is stable.
"""

import json
import sys
from pathlib import Path

from app.main import create_app


def export_openapi(path: Path) -> None:
    schema = create_app().openapi()
    path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m app.openapi_export <path>", file=sys.stderr)
        return 2
    export_openapi(Path(argv[0]))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
