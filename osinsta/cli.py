"""Osinsta CLI — interactive + one-shot modes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from . import __version__
from .commands import COMMANDS, run_command
from .config import ROOT, resolve_hiker_token, save_hiker_token
from .service import HikerAPIError, OsinstaError, build_service, verify_token

app = typer.Typer(add_completion=False, no_args_is_help=False, help="Osinsta — Instagram public OSINT (HikerAPI only)")
console = Console()


def _print_banner() -> None:
    console.print(
        Panel.fit(
            f"[bold cyan]OSINSTA[/] v{__version__}\n"
            "[dim]Instagram public OSINT · HikerAPI only · no IG login[/]",
            border_style="cyan",
        )
    )


def _ensure_token() -> str:
    token = resolve_hiker_token()
    if token:
        return token
    console.print("[yellow]No HikerAPI token found.[/]")
    token = Prompt.ask("Paste HikerAPI token").strip()
    if not token:
        console.print("[red]Token required.[/]")
        raise typer.Exit(1)
    save = Prompt.ask("Save to config/credentials.ini?", choices=["y", "n"], default="y")
    if save == "y":
        save_hiker_token(token)
        console.print("[green]Saved.[/]")
    return token


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    target: Optional[str] = typer.Option(None, "--target", "-t", help="Instagram username"),
    command: Optional[str] = typer.Option(None, "--command", "-c", help="Command name to run once"),
    web: bool = typer.Option(False, "--web", help="Start web UI on http://127.0.0.1:8787"),
    port: int = typer.Option(8787, "--port", help="Web UI port"),
    token: Optional[str] = typer.Option(None, "--token", help="HikerAPI token (or set HIKERAPI_TOKEN)"),
    list_commands: bool = typer.Option(False, "--list", help="List all commands"),
    params_json: Optional[str] = typer.Option(None, "--params", help='JSON object of command params, e.g. \'{"limit":50}\''),
):
    if ctx.invoked_subcommand is not None:
        return

    if list_commands:
        table = Table(title="Osinsta commands")
        table.add_column("Group")
        table.add_column("Command")
        table.add_column("Needs target")
        table.add_column("Description")
        for c in COMMANDS:
            table.add_row(c.group, c.name, "yes" if c.needs_target else "no", c.description)
        console.print(table)
        return

    if web:
        import uvicorn
        from .web.app import app as fastapi_app

        _print_banner()
        console.print(f"[cyan]Web UI →[/] http://127.0.0.1:{port}")
        uvicorn.run(fastapi_app, host="127.0.0.1", port=port, log_level="info")
        return

    _print_banner()
    from .config import set_runtime_token

    if token:
        set_runtime_token(token)

    tok = token or _ensure_token()

    if command:
        tgt = target
        cmd_meta = next((c for c in COMMANDS if c.name == command), None)
        if not cmd_meta:
            console.print(f"[red]Unknown command:[/] {command}")
            raise typer.Exit(1)
        if cmd_meta.needs_target and not tgt:
            console.print("[red]This command needs --target[/]")
            raise typer.Exit(1)
        params = json.loads(params_json) if params_json else {}
        try:
            service = build_service(tgt, tok)
            result = run_command(service, command, params)
            console.print_json(data=result)
            console.print(f"[dim]API calls: {service.api_call_count}[/]")
        except OsinstaError as e:
            console.print(f"[red]{e}[/]")
            raise typer.Exit(1)
        return

    # Interactive shell
    tgt = (target or Prompt.ask("Target username (blank for hashtag/location only)", default="")).strip().lstrip("@") or None
    try:
        service = build_service(tgt, tok)
    except OsinstaError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)

    if tgt:
        console.print(f"[green]Target:[/] @{service.target}  private={service.is_private}")
    else:
        console.print("[dim]No target — search_hashtag / search_location available[/]")

    by_group: dict[str, list] = {}
    for c in COMMANDS:
        by_group.setdefault(c.group, []).append(c)

    while True:
        console.print()
        for group, cmds in by_group.items():
            console.print(f"[bold]{group}[/]")
            for i, c in enumerate(cmds):
                # global index later
                pass
        table = Table(show_header=True, header_style="bold")
        table.add_column("#", style="cyan", width=4)
        table.add_column("Command")
        table.add_column("Group")
        table.add_column("Description")
        for idx, c in enumerate(COMMANDS, 1):
            table.add_row(str(idx), c.name, c.group, c.description)
        console.print(table)
        choice = Prompt.ask("Command # / name (q quit, t change target)", default="q").strip()
        if choice.lower() in ("q", "quit", "exit"):
            break
        if choice.lower() in ("t", "target"):
            tgt = Prompt.ask("New target").strip().lstrip("@") or None
            try:
                service = build_service(tgt, tok)
                console.print(f"[green]Target:[/] @{service.target}" if tgt else "[dim]No target[/]")
            except OsinstaError as e:
                console.print(f"[red]{e}[/]")
            continue

        cmd_name = None
        if choice.isdigit():
            n = int(choice)
            if 1 <= n <= len(COMMANDS):
                cmd_name = COMMANDS[n - 1].name
        else:
            cmd_name = choice

        if not cmd_name or not any(c.name == cmd_name for c in COMMANDS):
            console.print("[red]Unknown command[/]")
            continue

        meta = next(c for c in COMMANDS if c.name == cmd_name)
        if meta.needs_target and not service.target:
            console.print("[red]Set a target first (t)[/]")
            continue

        params: dict = {}
        for p in meta.params:
            raw = Prompt.ask(f"{p.name} ({p.description})", default="" if p.default is None else str(p.default))
            if raw == "" and p.default is None:
                continue
            params[p.name] = raw if p.type == "string" else (int(raw) if raw else p.default)

        try:
            # rebuild to reset call counter / refresh user if needed
            service = build_service(service.target, tok)
            result = run_command(service, cmd_name, params)
            out_dir = ROOT / "output"
            out_dir.mkdir(exist_ok=True)
            out_file = out_dir / f"{service.target or 'search'}_{cmd_name}.json"
            out_file.write_text(json.dumps(result, indent=2, default=str))
            console.print_json(data=result)
            console.print(f"[dim]API calls: {service.api_call_count} · saved {out_file}[/]")
        except OsinstaError as e:
            console.print(f"[red]{e}[/]")
        except Exception as e:
            console.print(f"[red]Unexpected:[/] {e}")


@app.command("set-token")
def set_token(token: str = typer.Argument(..., help="HikerAPI token")):
    """Verify and save a HikerAPI token."""
    try:
        verify_token(token)
    except Exception as e:
        console.print(f"[red]Token check failed:[/] {e}")
        raise typer.Exit(1)
    path = save_hiker_token(token)
    console.print(f"[green]Token saved to[/] {path}")


@app.command("web")
def web_cmd(port: int = typer.Option(8787, "--port")):
    """Start the web UI."""
    import uvicorn
    from .web.app import app as fastapi_app

    _print_banner()
    console.print(f"[cyan]Web UI →[/] http://127.0.0.1:{port}")
    uvicorn.run(fastapi_app, host="127.0.0.1", port=port, log_level="info")


def run() -> None:
    app()


if __name__ == "__main__":
    run()
