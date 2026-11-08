"""Export the OpenAPI document to docs/openapi.json (frontend handoff input).

Usage (from backend/): python -m app.scripts.export_openapi
"""

import json
from pathlib import Path

from app.main import app


def main() -> None:
    doc = app.openapi()
    out = Path(__file__).resolve().parents[2].parent / "docs" / "openapi.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(f"wrote {out} ({len(doc.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()
