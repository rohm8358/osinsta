"""Evidence pack export (JSON + standalone HTML report)."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .config import ROOT

EXPORT_DIR = ROOT / "output" / "reports"


def _now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def export_evidence(title: str, target: Optional[str], sections: dict[str, Any]) -> dict:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in (target or title or "report"))[:40]
    base = EXPORT_DIR / f"{slug}_{_now_slug()}"
    payload = {
        "title": title,
        "target": target,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tool": "Osinsta",
        "sections": sections,
    }
    json_path = Path(str(base) + ".json")
    html_path = Path(str(base) + ".html")
    json_path.write_text(json.dumps(payload, indent=2, default=str))
    html_path.write_text(_render_html(payload))
    return {"json": str(json_path), "html": str(html_path), "title": title, "target": target}


def _render_html(payload: dict) -> str:
    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'/>",
        f"<title>{html.escape(str(payload.get('title') or 'Osinsta report'))}</title>",
        "<style>body{font-family:IBM Plex Sans,Segoe UI,sans-serif;background:#0e1116;color:#e6edf3;margin:2rem}"
        "h1{color:#3dd6c6}h2{color:#8b9bb0;text-transform:uppercase;font-size:0.9rem;letter-spacing:.08em}"
        "pre{background:#0b0e13;border:1px solid #2a3340;border-radius:8px;padding:1rem;overflow:auto}"
        ".meta{color:#8b9bb0}</style></head><body>",
        f"<h1>{html.escape(str(payload.get('title') or 'Osinsta evidence'))}</h1>",
        f"<p class='meta'>Target: @{html.escape(str(payload.get('target') or '-'))} · "
        f"{html.escape(str(payload.get('generated_at') or ''))} · Osinsta</p>",
    ]
    for name, data in (payload.get("sections") or {}).items():
        parts.append(f"<h2>{html.escape(str(name))}</h2>")
        parts.append(f"<pre>{html.escape(json.dumps(data, indent=2, default=str))}</pre>")
    parts.append("</body></html>")
    return "\n".join(parts)
