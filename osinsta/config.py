"""Resolve HikerAPI token from env, runtime, or config file."""

from __future__ import annotations

import configparser
import os
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CREDENTIALS = ROOT / "config" / "credentials.ini"

_runtime_token: Optional[str] = None


def set_runtime_token(token: Optional[str]) -> None:
    global _runtime_token
    _runtime_token = (token or "").strip() or None


def get_runtime_token() -> Optional[str]:
    return _runtime_token


def resolve_hiker_token(credentials_path: Path | str | None = None) -> Optional[str]:
    token = (os.getenv("HIKERAPI_TOKEN") or "").strip()
    if token:
        return token
    if _runtime_token:
        return _runtime_token
    path = Path(credentials_path) if credentials_path else DEFAULT_CREDENTIALS
    try:
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(path)
        return (parser.get("Credentials", "hikerapi_token", fallback="") or "").strip() or None
    except Exception:
        return None


def save_hiker_token(token: str, credentials_path: Path | str | None = None) -> Path:
    path = Path(credentials_path) if credentials_path else DEFAULT_CREDENTIALS
    path.parent.mkdir(parents=True, exist_ok=True)
    parser = configparser.ConfigParser(interpolation=None)
    if path.exists():
        parser.read(path)
    if "Credentials" not in parser:
        parser["Credentials"] = {}
    parser["Credentials"]["hikerapi_token"] = token.strip()
    with path.open("w") as fh:
        parser.write(fh)
    set_runtime_token(token)
    return path


def mask_token(token: Optional[str]) -> Optional[str]:
    token = (token or "").strip()
    if not token:
        return None
    if len(token) <= 10:
        return "••••••••"
    return f"{token[:4]}…{token[-4:]}"


def hiker_balance(token: Optional[str] = None) -> Optional[dict]:
    """Free HikerAPI /sys/balance → remaining requests + amount."""
    tok = (token or resolve_hiker_token() or "").strip()
    if not tok:
        return None
    from hikerapi import Client

    client = Client(token=tok)
    try:
        data = client._request("get", "/sys/balance")
    except Exception as e:
        raise RuntimeError(str(e)) from e
    finally:
        try:
            client._client.close()
        except Exception:
            pass
    if not isinstance(data, dict) or "requests" not in data:
        detail = (data or {}).get("detail") if isinstance(data, dict) else None
        raise RuntimeError(str(detail or data)[:200])
    return {
        "requests": data.get("requests"),
        "amount": data.get("amount"),
        "currency": data.get("currency"),
    }
