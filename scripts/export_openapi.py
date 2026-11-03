"""Export the FastAPI OpenAPI schema to docs/openapi.json."""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    sys.path.insert(0, str(ROOT / "backend"))
    from agent.app import create_app

    with tempfile.TemporaryDirectory() as directory:
        schema = create_app(directory).openapi()
    output = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
    (ROOT / "docs" / "openapi.json").write_text(output)


if __name__ == "__main__":
    main()
