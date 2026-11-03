import json
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
from agent.app import create_app

with tempfile.TemporaryDirectory() as directory:
    schema = create_app(directory).openapi()
(root / "docs" / "openapi.json").write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n")
