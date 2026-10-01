"""Watch mode: snapshot public profile fields and diff changes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .config import ROOT
from .service import OsinstaService

WATCH_DIR = ROOT / "watch"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(username: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in username.lower())
    return WATCH_DIR / f"{safe}.json"


def snapshot_profile(service: OsinstaService) -> dict:
    info = service.get_user_info()
    about = {}
    try:
        about = service.get_account_about()
    except Exception as e:
        about = {"error": str(e)}
    snap = {
        "username": service.target,
        "captured_at": _now(),
        "is_private": service.is_private,
        "full_name": info.get("full_name"),
        "biography": info.get("biography"),
        "follower_count": info.get("follower_count"),
        "following_count": info.get("following_count"),
        "media_count": info.get("media_count"),
        "external_url": info.get("external_url"),
        "public_email": info.get("public_email"),
        "contact_phone_number": info.get("contact_phone_number"),
        "profile_pic_url_hd": info.get("profile_pic_url_hd"),
        "about_country": about.get("country"),
        "about_joined": about.get("date_joined"),
        "former_usernames_count": about.get("former_usernames_count"),
        "bio_links": info.get("bio_links") or [],
    }
    WATCH_DIR.mkdir(parents=True, exist_ok=True)
    path = _path(service.target or "unknown")
    history = {"username": service.target, "snapshots": []}
    if path.exists():
        try:
            history = json.loads(path.read_text())
        except Exception:
            pass
    history.setdefault("snapshots", []).append(snap)
    # keep last 30
    history["snapshots"] = history["snapshots"][-30:]
    path.write_text(json.dumps(history, indent=2, default=str))
    return {"saved": str(path), "snapshot": snap, "total_snapshots": len(history["snapshots"])}


def _diff(a: dict, b: dict) -> list[dict]:
    keys = [
        "full_name", "biography", "follower_count", "following_count", "media_count",
        "external_url", "public_email", "contact_phone_number", "profile_pic_url_hd",
        "about_country", "about_joined", "former_usernames_count", "is_private",
    ]
    changes = []
    for k in keys:
        if a.get(k) != b.get(k):
            changes.append({"field": k, "from": a.get(k), "to": b.get(k)})
    # bio links compare by urls
    a_links = sorted([(x.get("url") or "") for x in (a.get("bio_links") or []) if isinstance(x, dict)])
    b_links = sorted([(x.get("url") or "") for x in (b.get("bio_links") or []) if isinstance(x, dict)])
    if a_links != b_links:
        changes.append({"field": "bio_links", "from": a_links, "to": b_links})
    return changes


def watch_diff(username: str) -> dict:
    path = _path(username)
    if not path.exists():
        return {"username": username, "error": "No snapshots yet. Run watch_snapshot first."}
    history = json.loads(path.read_text())
    snaps = history.get("snapshots") or []
    if len(snaps) < 2:
        return {
            "username": username,
            "snapshots": len(snaps),
            "changes": [],
            "note": "Need at least 2 snapshots to diff.",
            "latest": snaps[-1] if snaps else None,
        }
    older, newer = snaps[-2], snaps[-1]
    return {
        "username": username,
        "snapshots": len(snaps),
        "from": older.get("captured_at"),
        "to": newer.get("captured_at"),
        "changes": _diff(older, newer),
        "changed": bool(_diff(older, newer)),
    }


def watch_and_diff(service: OsinstaService) -> dict:
    saved = snapshot_profile(service)
    diff = watch_diff(service.target or "")
    return {"snapshot": saved, "diff": diff}
