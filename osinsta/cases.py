"""Multi-target investigation case board."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .config import ROOT

CASES_DIR = ROOT / "cases"
SAFE_NAME = re.compile(r"[^a-zA-Z0-9._\-]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _case_path(case_id: str) -> Path:
    safe = SAFE_NAME.sub("_", case_id).strip("._") or "case"
    return CASES_DIR / f"{safe}.json"


def ensure_dirs() -> None:
    CASES_DIR.mkdir(parents=True, exist_ok=True)


def list_cases() -> list[dict]:
    ensure_dirs()
    rows = []
    for path in sorted(CASES_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            rows.append({
                "id": data.get("id") or path.stem,
                "title": data.get("title"),
                "targets": [t.get("username") for t in data.get("targets") or []],
                "updated_at": data.get("updated_at"),
                "created_at": data.get("created_at"),
            })
        except Exception:
            continue
    return rows


def load_case(case_id: str) -> dict:
    path = _case_path(case_id)
    if not path.exists():
        raise FileNotFoundError(f"Case not found: {case_id}")
    return json.loads(path.read_text())


def save_case(case: dict) -> dict:
    ensure_dirs()
    case["updated_at"] = _now()
    path = _case_path(case["id"])
    path.write_text(json.dumps(case, indent=2, default=str))
    return case


def create_case(title: str, targets: Optional[list[str]] = None, notes: str = "") -> dict:
    case_id = SAFE_NAME.sub("_", title.lower()).strip("._")[:40] or uuid.uuid4().hex[:8]
    if _case_path(case_id).exists():
        case_id = f"{case_id}_{uuid.uuid4().hex[:4]}"
    case = {
        "id": case_id,
        "title": title or case_id,
        "notes": notes or "",
        "created_at": _now(),
        "updated_at": _now(),
        "targets": [],
        "findings": [],
        "snapshots": {},
    }
    for username in targets or []:
        add_target(case, username)
    return save_case(case)


def add_target(case: dict, username: str, tags: Optional[list[str]] = None, note: str = "") -> dict:
    username = username.strip().lstrip("@").lower()
    if not username:
        raise ValueError("Empty username")
    existing = {t["username"] for t in case.get("targets") or []}
    if username not in existing:
        case.setdefault("targets", []).append({
            "username": username,
            "tags": tags or [],
            "note": note,
            "added_at": _now(),
        })
    return save_case(case)


def add_finding(case: dict, username: str, kind: str, data: Any, summary: str = "") -> dict:
    case.setdefault("findings", []).append({
        "id": uuid.uuid4().hex[:10],
        "username": (username or "").lstrip("@"),
        "kind": kind,
        "summary": summary,
        "data": data,
        "at": _now(),
    })
    return save_case(case)


def delete_case(case_id: str) -> bool:
    path = _case_path(case_id)
    if path.exists():
        path.unlink()
        return True
    return False
