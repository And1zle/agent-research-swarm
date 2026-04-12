"""Click command handlers for Agent Research Swarm."""

import asyncio
import sys

import click
from rich import box
from rich.panel import Panel
from rich.table import Table

from cli.core import load_config, save_config, default_config, build_agents
from cli.detector import detect_servers, best_server
from cli.presets import PRESETS, apply_preset, list_presets
from cli.visual import console, print_server_table, print_model_table, print_agent_summary
from cli.wizard import run_wizard
from cli.chat import run_chat


# ── Shared helpers ────────────────────────────────────────────────────────────

def _load_or_setup(config_path: str) -> dict:
    """Load config, or trigger setup wizard if missing."""
    config = load_config(config_path)
    if config is None:
        console.print(f"[yellow]No config found at {config_path}.[/yellow]")
        console.print("[dim]Starting setup wizard...[/dim]\n")
        config = run_wizard(config_path)
    return config


def _check_models_assigned(config: dict) -> bool:
    """Warn if any agent has an empty model assignment."""
    agents = config.get("agents", {})
    empty = [k for k, v in agents.items() if not v.get("model", "").strip()]
    if empty:
        console.print(f"[yellow]⚠ No model assigned for: {', '.join(empty)}[/yellow]")
        console.print("[dim]Run 'swarm setup' to assign models, or use 'swarm query --pick'.[/dim]\n")
        return False
    return True


# ── setup ─────────────────────────────────────────────────────────────────────

@click.command()
@click.option("--config", "config_path", default="config.yaml", help="Config file path")
def setup(config_path):
    """Interactive first-time setup — detect servers and assign models."""
    run_wizard(config_path)


# ── status ────────────────────────────────────────────────────────────────────

@click.command()
@click.option("--config", "config_path", default="config.yaml", help="Config file path")
def status(config_path):
    """Check server connectivity and show loaded models."""
    console.print()
    console.print("[cyan]Scanning for LLM servers...[/cyan]")
    servers = detect_servers(force=True)

    if not servers:
        console.print("[red]✗ No servers found.[/red]")
        console.print("[dim]Is LM Studio or Ollama running?[/dim]\n")
        sys.exit(1)

    print_server_table(servers)
    console.print()

    # Show current config model assignments if config exists
    config = load_config(config_path)
    if config:
        agents = build_agents(config)
        table = Table(title="Current Model Assignments", box=box.SIMPLE_HEAD, border_style="dim")
        table.add_column("Agent",  style="cyan")
        table.add_column("Model",  style="dim")
        table.add_column("Temp",   justify="right", style="dim")
        for key, agent in agents.items():
            model = agent["model"] or "[red]not set[/red]"
            table.add_row(
                f"{agent['emoji']} {agent['role']}",
                model,
                str(agent["temperature"])
            )
        console.print(table)
    else:
        console.print(f"[yellow]No config at {config_path}. Run 'swarm setup' to configure.[/yellow]")

    console.print()


# ── query ─────────────────────────────────────────────────────────────────────

@click.command()
@click.argument("question", required=False)
@click.option("--config",    "config_path", default="config.yaml", help="Config file path")
@click.option("--preset",    default=None,  help="Preset template: research, code-review, market, debug")
@click.option("--pick",      is_flag=True,  help="Interactively pick models before running")
@click.option("--debug",     is_flag=True,  help="Show raw agent outputs including <think> tags")
@click.option("--models",    is_flag=True,  help="List available models and exit")
@click.option("--from-file", "from_file",   default=None, type=click.Path(exists=True),
              help="Load the query/brief from a text file")
@click.option("--mode",      default=None,  type=click.Choice(["a", "b", "c"], case_sensitive=False),
              help="Skip mode prompt: a=standard, b=deep brief, c=genealogy")
@click.option("--parallel",  "n_parallel",  default=1, type=int,
              help="Number of parallel researcher agents (default 1)")
def query(question, config_path, preset, pick, debug, models, from_file, mode, n_parallel):
    """Run a single research query through the agent swarm."""
    from cli.core import run_swarm

    config = _load_or_setup(config_path)

    # --models: list and exit
    if models:
        servers = detect_servers()
        if not servers:
            console.print("[yellow]No servers found.[/yellow]")
            return
        for srv in servers:
            print_model_table(srv.models, title=f"{srv.name} Models")
        return

    # --pick: interactive model reassignment
    if pick:
        config = _interactive_pick(config)

    config = _auto_fix_server(config)
    _preflight_load_if_needed(config)

    if not _check_models_assigned(config):
        if click.confirm("Run setup wizard now?"):
            config = run_wizard(config_path)

    if preset:
        if preset not in PRESETS:
            console.print(f"[red]Unknown preset '{preset}'. Available: {', '.join(PRESETS)}[/red]")
            return
        config = apply_preset(config, preset)
        console.print(f"[green]✓[/green] Preset applied: [magenta]{preset}[/magenta]\n")

    # --from-file: load brief — always runs mode B
    if from_file:
        with open(from_file, encoding="utf-8") as f:
            question = f.read().strip()
        console.print(f"[green]✓[/green] Brief loaded from [dim]{from_file}[/dim] ({len(question)} chars)\n")
        mode = "b"

    # Mode selection — ask if not already decided
    if mode is None:
        console.print("[bold]Select research mode:[/bold]")
        console.print("  [cyan]A[/cyan]  Standard    — query broken into subtasks, agents research each one")
        console.print("  [cyan]B[/cyan]  Deep brief  — structured brief injected into all agents, up to 6 subtasks")
        console.print("  [cyan]C[/cyan]  Genealogy   — specialized agents for family tree research, outputs GEDCOM\n")
        raw = console.input("  Mode [dim](A/B/C, default A):[/dim] ").strip().lower()
        mode = raw if raw in ("a", "b", "c") else "a"
        console.print()

    deep_brief  = (mode in ("b", "c"))
    genealogy   = (mode == "c")

    # Genealogy mode: auto-apply genealogy preset
    if genealogy:
        config = apply_preset(config, "genealogy")
        console.print("[green]✓[/green] Genealogy preset applied [dim](specialized agents for all roles)[/dim]\n")

    # Parallel agents prompt (only when not passed as flag)
    if n_parallel == 1:
        console.print("[bold]Run multiple researcher agents in parallel?[/bold]")
        console.print("  [dim]1[/dim]  Sequential [dim](default — one subtask at a time)[/dim]")
        console.print("  [dim]2[/dim]  2 parallel  [dim](2x faster research step)[/dim]")
        console.print("  [dim]3[/dim]  3 parallel  [dim](fastest)[/dim]\n")
        raw = console.input("  Parallel researchers [dim](1/2/3, default 1):[/dim] ").strip()
        n_parallel = int(raw) if raw.isdigit() and int(raw) in (1, 2, 3) else 1
        console.print()

    # Get the query/brief
    if not question:
        if deep_brief:
            if genealogy:
                console.print("[bold]Paste your known family tree data below.[/bold]")
                console.print("[dim]Include all known ancestors, dates, and historical context.[/dim]")
                console.print("[dim]You can also load from a file with --from-file.[/dim]")
            else:
                console.print("[bold]Paste your research brief below.[/bold]")
            console.print("[dim]Enter a blank line followed by END when done:[/dim]\n")
            lines = []
            while True:
                line = input()
                if line.strip().upper() == "END":
                    break
                lines.append(line)
            question = "\n".join(lines).strip()
        else:
            question = console.input("[bold yellow]Research query:[/bold yellow] ").strip()

    if not question:
        console.print("[red]No query provided.[/red]")
        return

    if genealogy:
        console.print("\n[green]Genealogy mode[/green] [dim]— specialized agents, GEDCOM output, up to 6 research threads[/dim]\n")
    elif deep_brief:
        console.print("\n[magenta]Deep brief mode[/magenta] [dim]— brief injected into all agents, up to 6 subtasks[/dim]\n")

    asyncio.run(run_swarm(question, config, debug=debug, deep_brief=deep_brief, n_parallel=n_parallel))


# ── chat ──────────────────────────────────────────────────────────────────────

@click.command()
@click.option("--config", "config_path", default="config.yaml", help="Config file path")
@click.option("--preset", default=None,  help="Preset template: research, code-review, market, debug")
@click.option("--debug",  is_flag=True,  help="Show raw agent outputs including <think> tags")
def chat(config_path, preset, debug):
    """Multi-turn conversation mode — maintains context across queries."""
    config = _load_or_setup(config_path)
    config = _auto_fix_server(config)
    _preflight_load_if_needed(config)

    if not _check_models_assigned(config):
        if click.confirm("Run setup wizard now?"):
            config = run_wizard(config_path)
            return

    if preset:
        if preset not in PRESETS:
            console.print(f"[red]Unknown preset '{preset}'.[/red]")
            return
        config = apply_preset(config, preset)
        console.print(f"[green]✓[/green] Preset: [magenta]{preset}[/magenta]\n")

    run_chat(config, debug=debug, preset=preset)


# ── presets ───────────────────────────────────────────────────────────────────

@click.command()
def presets():
    """Show available preset templates."""
    console.print()
    table = Table(title="Available Presets", box=box.SIMPLE_HEAD, border_style="dim")
    table.add_column("Name",        style="magenta")
    table.add_column("Label",       style="cyan")
    table.add_column("Description", style="dim")

    for name, p in PRESETS.items():
        table.add_row(name, f"{p['emoji']} {p['name']}", p["description"])

    console.print(table)
    console.print()
    console.print("[dim]Usage: swarm query --preset research \"your question\"[/dim]")
    console.print("[dim]       swarm chat --preset code-review[/dim]\n")


# ── config ────────────────────────────────────────────────────────────────────

@click.group()
def config():
    """Manage configuration."""
    pass


@config.command("show")
@click.option("--config", "config_path", default="config.yaml", help="Config file path")
def config_show(config_path):
    """Show current configuration."""
    cfg = load_config(config_path)
    if cfg is None:
        console.print(f"[yellow]No config found at {config_path}.[/yellow]")
        return
    import yaml
    console.print()
    console.print(Panel(
        yaml.dump(cfg, default_flow_style=False, allow_unicode=True),
        title=f"[dim]{config_path}[/dim]",
        border_style="dim",
        box=box.MINIMAL
    ))


@config.command("edit")
@click.option("--config", "config_path", default="config.yaml", help="Config file path")
def config_edit(config_path):
    """Re-run the setup wizard to update configuration."""
    run_wizard(config_path)


# ── Internal utilities ────────────────────────────────────────────────────────

def _interactive_pick(config: dict) -> dict:
    """Let user reassign models interactively (keeps current as default)."""
    console.print("[cyan]Scanning for models...[/cyan]")
    servers = detect_servers(force=True)
    models = []
    if servers:
        srv    = best_server(servers)
        models = srv.models if srv else []

    if models:
        print_model_table(models)
        console.print()
    else:
        console.print("[yellow]No models detected — enter model names manually.[/yellow]\n")

    agents_config = config.get("agents", {})
    for key in ["coordinator", "researcher", "analyst", "summarizer", "code"]:
        current = agents_config.get(key, {}).get("model", "not set")
        if models:
            prompt = (
                f"[bold]{key}[/bold] [dim](current: {current})[/dim] "
                f"[dim]#{1}-{len(models)} or name or Enter to keep:[/dim] "
            )
        else:
            prompt = f"[bold]{key}[/bold] [dim](current: {current})[/dim] [dim]name or Enter:[/dim] "

        user_input = console.input(prompt).strip()
        if not user_input:
            continue
        if models and user_input.isdigit():
            idx = int(user_input) - 1
            user_input = models[idx] if 0 <= idx < len(models) else current

        agents_config.setdefault(key, {})["model"] = user_input
        console.print(f"  [green]✓[/green] {key} → {user_input}")

    config["agents"] = agents_config
    console.print()
    return config


def _preflight_load_if_needed(config: dict) -> None:
    """Silently check if assigned models are loaded; prompt to load any that aren't.

    No-op if the LM Studio management API is unavailable (Ollama, remote servers, etc.).
    """
    try:
        from cli.loader import is_management_api_available, get_loaded_models, load_model
        from cli.profiles import get_profile
    except ImportError:
        return

    server_url = config.get("server", {}).get("url", "")
    if not is_management_api_available(server_url):
        return  # Management API not available — skip silently

    loaded = get_loaded_models(server_url) or []
    loaded_lower = {m.lower() for m in loaded}

    agents_cfg = config.get("agents", {})
    assigned = {v.get("model", "").strip() for v in agents_cfg.values() if v.get("model", "").strip()}
    missing = [m for m in assigned if m.lower() not in loaded_lower]

    if not missing:
        return  # All models already loaded

    console.print("[bold]Model pre-flight check[/bold]")
    console.print("[dim]The following assigned models are not currently loaded:[/dim]")
    for m in missing:
        from cli.profiles import get_profile as _gp
        p = _gp(m)
        console.print(
            f"  [yellow]-[/yellow] [cyan]{m}[/cyan] "
            f"(GPU {int(p.gpu_offload_ratio * 100)}%, ctx {p.context_length}, {p.quant_recommendation})"
        )
    console.print()

    if click.confirm("  Load them now with optimal settings?", default=True):
        for model_id in missing:
            p = get_profile(model_id)
            console.print(f"  Loading [cyan]{model_id}[/cyan]...")
            ok = load_model(server_url, model_id, p)
            if ok:
                console.print(f"  [green]v[/green] {model_id} ready")
            else:
                console.print(f"  [yellow]! {model_id} load failed or timed out — continuing anyway[/yellow]")
        console.print()


def _auto_fix_server(config: dict) -> dict:
    """If configured server URL looks like a Tailscale/remote IP, suggest localhost."""
    url = config.get("server", {}).get("url", "")
    if "localhost" in url or "127.0.0.1" in url:
        return config  # looks fine

    servers = detect_servers()
    if servers:
        srv = best_server(servers)
        if srv and srv.url != url:
            console.print(
                f"[yellow]⚠ Configured server ({url}) may be unreachable.[/yellow]\n"
                f"[dim]Detected: {srv.name} at {srv.url}[/dim]"
            )
            if click.confirm(f"  Switch to {srv.url}?", default=True):
                config["server"]["url"] = srv.url
                console.print(f"[green]✓[/green] Using {srv.url}\n")
    return config
