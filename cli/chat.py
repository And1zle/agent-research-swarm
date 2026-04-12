"""Multi-turn conversation mode — maintains context across queries."""

import asyncio
from datetime import datetime
from pathlib import Path

from rich import box
from rich.panel import Panel

from cli.core import run_swarm
from cli.visual import console


def run_chat(config: dict, debug: bool = False, preset: str = None):
    """
    Interactive multi-turn conversation loop.
    Accumulates context from each completed research round.
    """
    console.print()
    console.print(Panel(
        "[bold cyan]🦞 Agent Research Swarm — Chat Mode[/bold cyan]\n"
        "[dim]Ask follow-up questions and the swarm will maintain context.[/dim]\n"
        "[dim]Commands: 'exit' or 'quit' to stop · 'clear' to reset context · 'save' to save session[/dim]",
        box=box.DOUBLE_EDGE,
        border_style="cyan"
    ))
    console.print()

    context_blocks  = []
    session_log     = []
    session_start   = datetime.now()
    turn            = 0

    while True:
        turn += 1
        try:
            query = console.input(f"[bold cyan]Query {turn}:[/bold cyan] ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not query:
            continue

        if query.lower() in ("exit", "quit", "q"):
            console.print("[dim]Exiting chat mode.[/dim]")
            break

        if query.lower() == "clear":
            context_blocks.clear()
            session_log.clear()
            turn = 0
            console.print("[yellow]Context cleared.[/yellow]\n")
            continue

        if query.lower() == "save":
            _save_session(session_log, session_start, preset)
            continue

        # Build context string from prior rounds
        context = "\n\n".join(context_blocks[-3:]) if context_blocks else ""  # last 3 rounds

        try:
            result = asyncio.run(run_swarm(
                query  = query,
                config = config,
                debug  = debug,
                context= context,
            ))
            report = result["report"]
            context_blocks.append(f"## Round {turn}: {query}\n{report}")
            session_log.append({"turn": turn, "query": query, "report": report})
        except KeyboardInterrupt:
            console.print("\n[yellow]Query interrupted.[/yellow]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    # Auto-save session if there were results
    if session_log:
        _save_session(session_log, session_start, preset)


def _save_session(session_log: list, start: datetime, preset: str = None):
    """Save the full chat session to a markdown file."""
    if not session_log:
        console.print("[dim]Nothing to save.[/dim]")
        return

    fname = f"swarm_chat_{start.strftime('%Y%m%d_%H%M%S')}.md"
    with open(fname, "w", encoding="utf-8") as f:
        f.write(f"# Research Swarm Chat Session\n\n")
        f.write(f"**Started:** {start.strftime('%Y-%m-%d %H:%M:%S')}\n")
        if preset:
            f.write(f"**Preset:** {preset}\n")
        f.write(f"**Turns:** {len(session_log)}\n\n---\n\n")
        for entry in session_log:
            f.write(f"## Turn {entry['turn']}: {entry['query']}\n\n")
            f.write(entry["report"])
            f.write("\n\n---\n\n")

    console.print(f"[dim]Chat session saved → {fname}[/dim]\n")
