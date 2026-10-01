"""FastAPI web UI for Osinsta."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import cases
from ..advanced import estimate_cost
from ..commands import COMMANDS, command_specs, run_command
from ..config import (
    get_runtime_token,
    hiker_balance,
    mask_token,
    resolve_hiker_token,
    save_hiker_token,
    set_runtime_token,
)
from ..service import OsinstaError, build_service, verify_token

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Osinsta", docs_url="/api/docs")


class TokenBody(BaseModel):
    token: str
    save: bool = True


class RunBody(BaseModel):
    command: str
    target: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict)
    case_id: Optional[str] = None


class BatchRunBody(BaseModel):
    commands: list[str]
    target: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict)
    case_id: Optional[str] = None
    profile_mode: Optional[str] = None  # private | public


class CaseCreate(BaseModel):
    title: str
    targets: list[str] = Field(default_factory=list)
    notes: str = ""


class CaseTargetBody(BaseModel):
    username: str
    note: str = ""
    tags: list[str] = Field(default_factory=list)


class CostBody(BaseModel):
    commands: list[str]


def _token_state() -> dict:
    token = resolve_hiker_token()
    balance = None
    if token:
        try:
            balance = hiker_balance(token)
        except Exception as e:
            balance = {"error": str(e)}
    return {
        "has_token": bool(token),
        "token_masked": mask_token(token),
        "balance": balance,
    }


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/settings")
def settings_page():
    return FileResponse(STATIC / "settings.html")


@app.get("/api/health")
def health():
    state = _token_state()
    return {
        "ok": True,
        "name": "osinsta",
        "version": "1.2.0",
        "backend": "HikerAPI",
        "commands": len(COMMANDS),
        **state,
        "features": [
            "multi_select",
            "private_public_filter",
            "case_board",
            "balance",
            "labeled_results",
        ],
    }


@app.get("/api/balance")
def balance():
    try:
        data = hiker_balance()
    except Exception as e:
        raise HTTPException(502, str(e)) from e
    if data is None:
        return {"available": False}
    return {"available": True, **data}


@app.get("/api/commands")
def commands():
    return command_specs()


@app.post("/api/token")
def set_token(body: TokenBody):
    token = body.token.strip()
    if not token:
        raise HTTPException(400, "Empty token")
    try:
        # Prefer balance check (free) — falls back to verify_token
        try:
            bal = hiker_balance(token)
        except Exception:
            verify_token(token)
            bal = None
    except Exception as e:
        raise HTTPException(400, f"Token rejected: {e}") from e
    set_runtime_token(token)
    path = None
    if body.save:
        path = str(save_hiker_token(token))
    return {"ok": True, "saved_to": path, "token_masked": mask_token(token), "balance": bal}


@app.post("/api/cost")
def cost(body: CostBody):
    return estimate_cost(body.commands)


@app.get("/api/cases")
def api_list_cases():
    return cases.list_cases()


@app.post("/api/cases")
def api_create_case(body: CaseCreate):
    return cases.create_case(body.title, body.targets, body.notes)


@app.get("/api/cases/{case_id}")
def api_get_case(case_id: str):
    try:
        return cases.load_case(case_id)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e


@app.post("/api/cases/{case_id}/targets")
def api_add_target(case_id: str, body: CaseTargetBody):
    try:
        case = cases.load_case(case_id)
        return cases.add_target(case, body.username, body.tags, body.note)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.delete("/api/cases/{case_id}")
def api_delete_case(case_id: str):
    if not cases.delete_case(case_id):
        raise HTTPException(404, "Case not found")
    return {"ok": True}


def _run_one(command: str, target: Optional[str], params: dict, case_id: Optional[str]) -> dict:
    service = build_service(target)
    result = run_command(service, command, params)
    if case_id:
        try:
            case = cases.load_case(case_id)
            cases.add_finding(case, service.target or "", command, result, f"Ran {command}")
        except FileNotFoundError:
            pass
    return {
        "ok": True,
        "command": command,
        "target": service.target,
        "api_calls": service.api_call_count,
        "result": result,
    }


@app.post("/api/run")
def run(body: RunBody):
    if not resolve_hiker_token() and not get_runtime_token():
        raise HTTPException(401, "Set a HikerAPI token first")
    try:
        return _run_one(body.command, body.target, body.params, body.case_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    except OsinstaError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"Unexpected error: {e}") from e


@app.post("/api/run_batch")
def run_batch(body: BatchRunBody):
    if not resolve_hiker_token() and not get_runtime_token():
        raise HTTPException(401, "Set a HikerAPI token first")
    if not body.commands:
        raise HTTPException(400, "No commands selected")
    results = []
    total_calls = 0
    for name in body.commands:
        try:
            # Rebuild service each command so call counts stay per-command clear
            item = _run_one(name, body.target, body.params.get(name, body.params), body.case_id)
            total_calls += item["api_calls"]
            results.append(item)
        except Exception as e:
            results.append({"ok": False, "command": name, "error": str(e), "api_calls": 0})
    bal = None
    try:
        bal = hiker_balance()
    except Exception:
        pass
    return {
        "ok": True,
        "target": (body.target or "").lstrip("@") or None,
        "profile_mode": body.profile_mode,
        "total_api_calls": total_calls,
        "results": results,
        "balance": bal,
    }


app.mount("/static", StaticFiles(directory=STATIC), name="static")
