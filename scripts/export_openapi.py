"""Write the FastAPI OpenAPI schema to apps/api/openapi.json (input for the generated TS client)."""
import json
from pathlib import Path

from apps.api.main import app

out = Path(__file__).resolve().parent.parent / "apps" / "api" / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=1), encoding="utf-8")
print(f"wrote {out}")
