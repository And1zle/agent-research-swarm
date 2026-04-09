"""Rich UI components for Agent Research Swarm."""

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

console = Console()


# ── Header / Panels ───────────────────────────────────────────────────────────

def print_header(query: str, server_url: str, web_search: bool, preset: str = None):
    preset_str = f" · preset: [magenta]{preset}[/magenta]" if preset else ""
    console.print()
    console.print(Panel(
        f"[bold cyan]🦞 Agent Research Swarm[/bold cyan]{preset_str}\n"
        f"[white]Query:[/white] [bold yellow]{query}[/bold yellow]\n"
        f"[dim]Server: {server_url} | Web search: {'Tavily ✓' if web_search else 'disabled'}[/dim]",
        box=box.DOUBLE_EDGE,
        border_style="cyan"
    ))
    console.print()


def print_step(step: int, total: int, emoji: str, role: str, model: str, extra: str = ""):
    extra_str = f" [dim]{extra}[/dim]" if extra else ""
    console.print(
        f"[bold cyan]Step {step}/{total}[/bold cyan] {emoji} {role} "
        f"[dim]({model})[/dim]{extra_str}"
    )


def print_success(msg: str):
    console.print(f"  [green]✓[/green] {msg}")


def print_warn(msg: str):
    console.print(f"  [yellow]⚠[/yellow] {msg}")


def print_subtasks(subtasks: list):
    for i, task in enumerate(subtasks, 1):
        console.print(f"    [dim]{i}.[/dim] {task}")
    console.print()


def print_final_report(report: str, elapsed: float):
    console.print()
    console.print(Panel(
        report,
        title="[bold green]📋 Final Research Report[/bold green]",
        subtitle=f"[dim]Completed in {elapsed:.1f}s[/dim]",
        border_style="green",
        box=box.ROUNDED
    ))


def print_debug_block(label: str, content: str):
    console.print(Panel(
        content,
        title=f"[dim yellow]🐛 DEBUG: {label}[/dim yellow]",
        border_style="yellow",
        box=box.MINIMAL
    ))


# ── Summary Table ─────────────────────────────────────────────────────────────

def print_agent_summary(agents: dict, web_search: bool, timings: dict, total: float):
    console.print()
    table = Table(title="Agent Summary", box=box.SIMPLE_HEAD, border_style="dim")
    table.add_column("Agent",  style="cyan")
    table.add_column("Model",  style="dim")
    table.add_column("Time",   justify="right", style="dim")
    table.add_column("Status", justify="center")

    if web_search:
        t = timings.get("web_search", 0)
        table.add_row("🌐 Web Search", "Tavily", f"{t:.1f}s" if t else "—", "[green]✓[/green]")

    for key, agent in agents.items():
        t = timings.get(key, 0)
        table.add_row(
            f"{agent['emoji']} {agent['role']}",
            agent["model"],
            f"{t:.1f}s" if t else "—",
            "[green]✓[/green]"
        )

    console.print(table)
    console.print(f"\n[dim]Total time: {total:.1f}s[/dim]")


# ── Server / Model Tables ─────────────────────────────────────────────────────

def print_server_table(servers: list):
    if not servers:
        console.print("[yellow]No servers detected. Is LM Studio or Ollama running?[/yellow]")
        return
    table = Table(title="Detected Servers", box=box.SIMPLE_HEAD, border_style="dim")
    table.add_column("#",       style="dim", width=4)
    table.add_column("Server",  style="cyan")
    table.add_column("URL",     style="dim")
    table.add_column("Models",  justify="right")
    table.add_column("Status",  justify="center")
    for i, srv in enumerate(servers, 1):
        status = "[green]✓ Online[/green]" if srv.available else "[red]✗ Offline[/red]"
        table.add_row(str(i), srv.name, srv.url, str(len(srv.models)), status)
    console.print(table)


def print_model_table(models: list, title: str = "Available Models"):
    if not models:
        console.print("[yellow]No models found.[/yellow]")
        return
    table = Table(title=title, box=box.SIMPLE_HEAD, border_style="dim")
    table.add_column("#",        style="dim", width=4)
    table.add_column("Model ID", style="cyan")
    for i, m in enumerate(models, 1):
        table.add_row(str(i), m)
    console.print(table)


# ── Progress helper ───────────────────────────────────────────────────────────

def make_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )
