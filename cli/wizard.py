"""Interactive first-run setup wizard."""

from rich import box
from rich.panel import Panel
from rich.table import Table

from cli.detector import detect_servers, best_server
from cli.core import default_config, save_config
from cli.visual import console, print_model_table, print_server_table
from cli.profiles import get_profile, is_known_model


def run_wizard(config_path: str = "config.yaml") -> dict:
    """
    Walk the user through setting up their config.yaml interactively.
    Returns the completed config dict.
    """
    console.print()
    console.print(Panel(
        "[bold cyan]Agent Research Swarm — Setup Wizard[/bold cyan]\n"
        "[dim]Let's configure your models. This only takes a minute.[/dim]",
        box=box.DOUBLE_EDGE,
        border_style="cyan"
    ))
    console.print()

    # ── Step 1: Detect servers ────────────────────────────────────────────
    console.print("[cyan]Scanning for local LLM servers...[/cyan]")
    servers = detect_servers(force=True)

    if not servers:
        console.print("[yellow]No servers detected (LM Studio / Ollama).[/yellow]")
        console.print("[dim]You can still configure manually.[/dim]\n")
        server_url = console.input(
            "[bold]Enter your LLM server URL[/bold] [dim](e.g. http://localhost:1234/v1):[/dim] "
        ).strip() or "http://localhost:1234/v1"
        models = []
    else:
        print_server_table(servers)
        console.print()

        if len(servers) == 1:
            chosen_server = servers[0]
            console.print(f"[green]v[/green] Using [cyan]{chosen_server.name}[/cyan] ({chosen_server.url})")
        else:
            for i, s in enumerate(servers, 1):
                console.print(f"  [{i}] {s.name} — {s.url}")
            choice = console.input("\n[bold]Select server[/bold] [dim](number or Enter for #1):[/dim] ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(servers):
                chosen_server = servers[int(choice) - 1]
            else:
                chosen_server = servers[0]
            console.print(f"[green]v[/green] Selected [cyan]{chosen_server.name}[/cyan]")

        server_url = chosen_server.url
        models     = chosen_server.models

    console.print()

    # ── Step 2: Assign models to agents ──────────────────────────────────
    console.print("[bold]Assign models to agents[/bold]")
    console.print("[dim]Press Enter to use the first available model for each agent.[/dim]\n")

    if models:
        print_model_table(models)
        console.print()

    agent_keys = ["coordinator", "researcher", "analyst", "summarizer", "code"]
    agent_info = {
        "coordinator": ("Coordinator",  "fast/small model recommended"),
        "researcher":  ("Researcher",   "mid-size works well"),
        "analyst":     ("Analyst",      "mid-size, lower temp"),
        "summarizer":  ("Summarizer",   "any quality model"),
        "code":        ("Code Agent",   "code-specialized if available"),
    }

    default_model = models[0] if models else ""
    assignments   = {}

    for key in agent_keys:
        label, hint = agent_info[key]
        prompt_str = (
            f"  {label} [dim]({hint})[/dim]\n"
            f"  [dim]Enter name or #{1}-{len(models)}, or Enter for default '{default_model}':[/dim] "
            if models else
            f"  {label} [dim]({hint})[/dim]\n"
            f"  [dim]Enter model name:[/dim] "
        )
        user_input = console.input(prompt_str).strip()

        if not user_input:
            chosen = default_model
        elif models and user_input.isdigit():
            idx = int(user_input) - 1
            chosen = models[idx] if 0 <= idx < len(models) else default_model
        else:
            chosen = user_input

        assignments[key] = chosen
        console.print(f"  [green]v[/green] {label} -> [cyan]{chosen}[/cyan]\n")

    # ── Step 3: Show model profiles ───────────────────────────────────────
    console.print()
    console.print("[bold]Model profiles[/bold] [dim](optimal load settings)[/dim]")
    profile_table = Table(box=box.SIMPLE_HEAD, border_style="dim")
    profile_table.add_column("Agent",    style="cyan")
    profile_table.add_column("Model",    style="dim")
    profile_table.add_column("GPU %",    justify="right")
    profile_table.add_column("Context",  justify="right", style="dim")
    profile_table.add_column("Quant",    style="dim")
    profile_table.add_column("KV Cache", style="dim")

    seen_models: dict[str, object] = {}  # model_id → profile (for dedup)
    for key in agent_keys:
        model_id = assignments.get(key, "")
        if not model_id:
            continue
        profile = get_profile(model_id)
        known   = is_known_model(model_id)
        quant   = profile.quant_recommendation
        if not known:
            quant = f"[dim]{quant}[/dim] [yellow](default)[/yellow]"
        profile_table.add_row(
            key,
            model_id,
            f"{int(profile.gpu_offload_ratio * 100)}%",
            str(profile.context_length),
            quant,
            profile.kv_cache_quant_type,
        )
        seen_models[model_id] = profile

    console.print(profile_table)
    console.print("[dim]  max_concurrent_predictions = 1 (all profiles)[/dim]\n")

    # ── Step 4: Offer auto-load via management API ────────────────────────
    try:
        from cli.loader import is_management_api_available, load_model, get_loaded_models
        mgmt_available = is_management_api_available(server_url)
    except ImportError:
        mgmt_available = False

    if mgmt_available:
        console.print("[bold]Auto-load with optimal settings?[/bold]")
        console.print(
            "[dim]The LM Studio management API is available. "
            "I can load your models now with the GPU offload, context, and KV cache settings shown above.[/dim]"
        )
        do_load = console.input("  Auto-load models now? [dim](Y/n):[/dim] ").strip().lower()
        if do_load in ("", "y", "yes"):
            loaded = get_loaded_models(server_url) or []
            loaded_lower = {m.lower() for m in loaded}
            unique_models = list(dict.fromkeys(assignments.values()))  # preserve order, dedup
            for model_id in unique_models:
                if not model_id:
                    continue
                if model_id.lower() in loaded_lower:
                    console.print(f"  [dim]{model_id} already loaded — skipping[/dim]")
                    continue
                profile = get_profile(model_id)
                console.print(
                    f"  Loading [cyan]{model_id}[/cyan] "
                    f"(GPU {int(profile.gpu_offload_ratio * 100)}%, "
                    f"ctx {profile.context_length}, {profile.quant_recommendation})..."
                )
                ok = load_model(server_url, model_id, profile)
                if ok:
                    console.print(f"  [green]v[/green] {model_id} loaded")
                else:
                    console.print(f"  [yellow]! {model_id} load failed or timed out[/yellow]")
        console.print()

    # ── Step 5: Tavily web search ─────────────────────────────────────────
    console.print("[bold]Web Search (optional)[/bold]")
    console.print("[dim]Tavily enables live web search during research. Leave blank to skip.[/dim]")
    tavily_key = console.input("  Tavily API key [dim](https://app.tavily.com):[/dim] ").strip()
    console.print()

    # ── Step 6: Build and save config ────────────────────────────────────
    config = default_config(server_url)
    for key, model in assignments.items():
        config["agents"][key]["model"] = model
    config["tavily_api_key"] = tavily_key

    # Preview
    console.print("[bold]Config preview:[/bold]")
    table = Table(box=box.SIMPLE_HEAD, border_style="dim", show_header=False)
    table.add_column("Key",   style="dim")
    table.add_column("Value", style="cyan")
    table.add_row("Server URL", server_url)
    table.add_row("Web search", "Tavily" if tavily_key else "disabled")
    for key, model in assignments.items():
        table.add_row(f"  agents.{key}", model)
    console.print(table)
    console.print()

    confirm = console.input("[bold]Save config to config.yaml?[/bold] [dim](Y/n):[/dim] ").strip().lower()
    if confirm in ("", "y", "yes"):
        save_config(config, config_path)
        console.print(f"\n[green]v Config saved to {config_path}[/green]\n")
    else:
        console.print("[yellow]Config not saved.[/yellow]\n")

    return config
