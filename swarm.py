#!/usr/bin/env python3
"""
🦞 Agent Research Swarm
Multi-agent research system using local LLMs via LM Studio or Ollama.

Usage:
  python swarm.py                    # prompt for query, use config.yaml models
  python swarm.py "your question"    # pass query directly
  python swarm.py --models           # list models available in your LM Studio
  python swarm.py --pick             # interactively assign models before running
  python swarm.py --pick "question"  # pick models, then run with this query
"""

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml
from openai import AsyncOpenAI
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# ── Optional Tavily web search ────────────────────────────────────────────────
try:
    from tavily import TavilyClient
    TAVILY_AVAILABLE = True
except ImportError:
    TAVILY_AVAILABLE = False

console = Console()


# ── Config loading ────────────────────────────────────────────────────────────

def load_config(path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    config_path = Path(path)
    if not config_path.exists():
        console.print(f"[red]Config file not found: {path}[/red]")
        console.print("[dim]Copy config.yaml.example to config.yaml and edit it.[/dim]")
        sys.exit(1)
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_agents(config: dict) -> dict:
    """Build agent definitions from config."""
    agent_meta = {
        "coordinator": {
            "emoji": "🎯",
            "role": "Coordinator",
            "system": (
                "You are a research coordinator. Given a research query, break it into "
                "3-4 focused sub-tasks for specialized agents. Be concise. "
                "Return ONLY a JSON array of strings, each string being a sub-task. "
                'Example: ["Find recent statistics on X", "Analyze trends in Y", "Summarize key findings about Z"]'
            ),
        },
        "researcher": {
            "emoji": "🔍",
            "role": "Researcher",
            "system": (
                "You are a research specialist. Given a specific research sub-task, "
                "provide thorough, factual findings. Be detailed but focused. "
                "Use your knowledge to provide the best possible answer."
            ),
        },
        "analyst": {
            "emoji": "📊",
            "role": "Analyst",
            "system": (
                "You are a data analyst. Analyze the research findings provided and "
                "identify key patterns, insights, and implications. Be analytical and precise."
            ),
        },
        "summarizer": {
            "emoji": "📝",
            "role": "Summarizer",
            "system": (
                "You are a professional summarizer. Take research findings and analysis, "
                "and produce a clear, well-structured final report. "
                "Use markdown formatting with headers and bullet points."
            ),
        },
        "code": {
            "emoji": "💻",
            "role": "Code Agent",
            "system": (
                "You are a coding expert. If the research involves technical or code-related topics, "
                "provide relevant code examples, implementations, or technical details. "
                "If not code-related, briefly note that no code is needed for this task."
            ),
        },
    }

    agents = {}
    for key, meta in agent_meta.items():
        agent_config = config.get("agents", {}).get(key, {})
        agents[key] = {
            **meta,
            "model": agent_config.get("model", "default-model"),
            "temperature": agent_config.get("temperature", 0.5),
            "max_tokens": agent_config.get("max_tokens", 800),
        }
    return agents


# ── Model listing ─────────────────────────────────────────────────────────────

async def fetch_available_models(client: AsyncOpenAI) -> list[str]:
    """Fetch the list of models available from the server."""
    try:
        response = await client.models.list()
        return [m.id for m in response.data]
    except Exception as e:
        return []


def print_models(models: list[str]):
    """Print available models in a table."""
    if not models:
        console.print("[yellow]No models found. Is LM Studio running with a model loaded?[/yellow]")
        return
    table = Table(title="Available Models", box=box.SIMPLE_HEAD, border_style="dim")
    table.add_column("#", style="dim", width=4)
    table.add_column("Model ID", style="cyan")
    for i, m in enumerate(models, 1):
        table.add_row(str(i), m)
    console.print(table)


# ── Interactive model picker ──────────────────────────────────────────────────

async def pick_models(config: dict, client: AsyncOpenAI) -> dict:
    """Interactively assign models to agents. Returns updated config."""
    models = await fetch_available_models(client)

    console.print()
    console.print("[bold cyan]Model Selection[/bold cyan]")
    console.print("[dim]Press Enter to keep the current assignment.[/dim]\n")

    if models:
        print_models(models)
        console.print()

    agents_config = config.get("agents", {})
    for agent_key in ["coordinator", "researcher", "analyst", "summarizer", "code"]:
        current = agents_config.get(agent_key, {}).get("model", "not set")

        if models:
            prompt_text = (
                f"[bold]{agent_key}[/bold] [dim](current: {current})[/dim] "
                f"[dim]Enter model name or #{1}-{len(models)}, or press Enter to keep:[/dim] "
            )
        else:
            prompt_text = (
                f"[bold]{agent_key}[/bold] [dim](current: {current})[/dim] "
                f"[dim]Enter model name or press Enter to keep:[/dim] "
            )

        user_input = console.input(prompt_text).strip()

        if not user_input:
            continue

        # Allow selecting by number
        if models and user_input.isdigit():
            idx = int(user_input) - 1
            if 0 <= idx < len(models):
                user_input = models[idx]
            else:
                console.print(f"  [red]Invalid number, keeping {current}[/red]")
                continue

        if agent_key not in agents_config:
            agents_config[agent_key] = {}
        agents_config[agent_key]["model"] = user_input
        console.print(f"  [green]✓[/green] {agent_key} → {user_input}")

    config["agents"] = agents_config
    console.print()
    return config


# ── Web search (optional) ─────────────────────────────────────────────────────

async def search_web(tavily, query: str, max_results: int = 8) -> str:
    """Search the web using Tavily and return formatted results."""
    query = query[:400]
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: tavily.search(query=query, max_results=max_results, search_depth="advanced")
        )
        formatted = []
        for r in response.get("results", []):
            formatted.append(
                f"**{r.get('title', 'No title')}**\n"
                f"URL: {r.get('url', '')}\n"
                f"{r.get('content', '')}"
            )
        return "\n\n---\n\n".join(formatted) if formatted else "No results found."
    except Exception as e:
        return f"[Search error: {e}]"


# ── Agent runner ──────────────────────────────────────────────────────────────

def strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks from model output (DeepSeek R1 etc.)."""
    import re
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


async def call_agent(client: AsyncOpenAI, agent: dict, prompt: str,
                     inference_params: dict) -> str:
    """Call a single agent and return its response."""
    params = {k: v for k, v in inference_params.items() if k != "seed" or v is not None}
    try:
        response = await client.chat.completions.create(
            model=agent["model"],
            messages=[
                {"role": "system", "content": agent["system"]},
                {"role": "user", "content": prompt},
            ],
            max_tokens=agent["max_tokens"],
            temperature=agent["temperature"],
            **params,
        )
        return strip_think_tags(response.choices[0].message.content.strip())
    except Exception as e:
        return f"[Agent error: {e}]"


def parse_subtasks(coordinator_output: str) -> list[str]:
    """Parse sub-tasks from coordinator JSON output."""
    try:
        start = coordinator_output.find("[")
        end = coordinator_output.rfind("]") + 1
        if start != -1 and end > start:
            return json.loads(coordinator_output[start:end])
    except Exception:
        pass
    lines = [l.strip().lstrip("0123456789.-) ") for l in coordinator_output.split("\n") if l.strip()]
    return [l for l in lines if len(l) > 10][:4]


# ── Main swarm pipeline ───────────────────────────────────────────────────────

async def run_swarm(query: str, config: dict):
    """Run the full multi-agent research pipeline."""
    server_url = config["server"]["url"]
    api_key = config["server"].get("api_key", "sk-local")
    tavily_key = config.get("tavily_api_key", "") or os.environ.get("TAVILY_API_KEY", "")
    inference_params = config.get("inference", {})
    agents = build_agents(config)

    client = AsyncOpenAI(base_url=server_url, api_key=api_key)
    tavily = TavilyClient(api_key=tavily_key) if (TAVILY_AVAILABLE and tavily_key) else None
    web_search_enabled = tavily is not None

    start_time = time.time()

    console.print()
    console.print(Panel(
        f"[bold cyan]🦞 Agent Research Swarm[/bold cyan]\n"
        f"[white]Query:[/white] [yellow]{query}[/yellow]\n"
        f"[dim]Server: {server_url} | Web search: {'Tavily ✓' if web_search_enabled else 'disabled'}[/dim]",
        box=box.DOUBLE_EDGE,
        border_style="cyan"
    ))
    console.print()

    # ── Step 1: Coordinator breaks down the query ─────────────────────────
    console.print(f"[bold cyan]Step 1/4[/bold cyan] {agents['coordinator']['emoji']} Coordinator planning sub-tasks "
                  f"[dim]({agents['coordinator']['model']})[/dim]...")
    with console.status("[cyan]Coordinator thinking...[/cyan]"):
        coordinator_output = await call_agent(
            client, agents["coordinator"],
            f"Research query: {query}\nBreak this into 3-4 focused sub-tasks.",
            inference_params
        )

    subtasks = parse_subtasks(coordinator_output)
    if not subtasks:
        subtasks = [query]

    console.print(f"  [green]✓[/green] {len(subtasks)} sub-tasks:")
    for i, task in enumerate(subtasks, 1):
        console.print(f"    [dim]{i}.[/dim] {task}")
    console.print()

    # ── Step 2: Research (with optional web search) ───────────────────────
    if web_search_enabled:
        console.print(f"[bold cyan]Step 2/4[/bold cyan] 🌐 Web search + "
                      f"{agents['researcher']['emoji']} Researcher "
                      f"[dim]({agents['researcher']['model']})[/dim]...")
        research_findings = []
        for i, task in enumerate(subtasks, 1):
            with console.status(f"[cyan]Searching + synthesizing sub-task {i}/{len(subtasks)}...[/cyan]"):
                search_result = await search_web(tavily, task)
                finding = await call_agent(
                    client, agents["researcher"],
                    f"Research sub-task: {task}\n\nWeb search results:\n{search_result}\n\nSynthesize these findings.",
                    inference_params
                )
            research_findings.append(f"### Sub-task {i}: {task}\n{finding}")
            console.print(f"  [green]✓[/green] Sub-task {i} complete ({len(finding)} chars)")
    else:
        console.print(f"[bold cyan]Step 2/4[/bold cyan] {agents['researcher']['emoji']} Researcher "
                      f"[dim]({agents['researcher']['model']})[/dim]...")
        research_findings = []
        for i, task in enumerate(subtasks, 1):
            with console.status(f"[cyan]Researching sub-task {i}/{len(subtasks)}...[/cyan]"):
                finding = await call_agent(
                    client, agents["researcher"],
                    f"Research sub-task: {task}\n\nProvide thorough findings.",
                    inference_params
                )
            research_findings.append(f"### Sub-task {i}: {task}\n{finding}")
            console.print(f"  [green]✓[/green] Sub-task {i} complete ({len(finding)} chars)")

    combined_research = "\n\n".join(research_findings)
    console.print()

    # ── Step 3: Analyst + Code Agent in parallel ──────────────────────────
    console.print(
        f"[bold cyan]Step 3/4[/bold cyan] "
        f"{agents['analyst']['emoji']} Analyst [dim]({agents['analyst']['model']})[/dim] + "
        f"{agents['code']['emoji']} Code Agent [dim]({agents['code']['model']})[/dim] "
        f"[dim](parallel)[/dim]..."
    )
    analyst_prompt = f"Original query: {query}\n\nResearch findings:\n{combined_research}\n\nProvide your analysis."
    code_prompt = f"Original query: {query}\n\nResearch findings:\n{combined_research}\n\nProvide relevant code examples or technical details if applicable."

    with console.status("[cyan]Analyst & Code Agent working in parallel...[/cyan]"):
        analyst_result, code_result = await asyncio.gather(
            call_agent(client, agents["analyst"], analyst_prompt, inference_params),
            call_agent(client, agents["code"], code_prompt, inference_params),
        )

    console.print(f"  [green]✓[/green] Analysis complete ({len(analyst_result)} chars)")
    console.print(f"  [green]✓[/green] Code agent complete ({len(code_result)} chars)")
    console.print()

    # ── Step 4: Summarizer produces final report ──────────────────────────
    console.print(f"[bold cyan]Step 4/4[/bold cyan] {agents['summarizer']['emoji']} Summarizer "
                  f"[dim]({agents['summarizer']['model']})[/dim]...")

    summary_prompt = (
        f"Original research query: {query}\n\n"
        f"## Research Findings\n{combined_research}\n\n"
        f"## Analysis\n{analyst_result}\n\n"
        f"## Technical Details\n{code_result}\n\n"
        "Write a comprehensive, well-structured final report."
    )

    with console.status("[cyan]Summarizer writing report...[/cyan]"):
        final_report = await call_agent(client, agents["summarizer"], summary_prompt, inference_params)

    elapsed = time.time() - start_time

    # ── Display final report ──────────────────────────────────────────────
    console.print()
    console.print(Panel(
        final_report,
        title="[bold green]📋 Final Research Report[/bold green]",
        subtitle=f"[dim]Completed in {elapsed:.1f}s[/dim]",
        border_style="green",
        box=box.ROUNDED
    ))

    # ── Agent summary table ───────────────────────────────────────────────
    console.print()
    table = Table(title="Agent Summary", box=box.SIMPLE_HEAD, border_style="dim")
    table.add_column("Agent", style="cyan")
    table.add_column("Model", style="dim")
    table.add_column("Status", justify="center")

    if web_search_enabled:
        table.add_row("🌐 Web Search", "Tavily", "[green]✓ Done[/green]")

    for key, agent in agents.items():
        table.add_row(f"{agent['emoji']} {agent['role']}", agent["model"], "[green]✓ Done[/green]")

    console.print(table)
    console.print(f"\n[dim]Total time: {elapsed:.1f}s[/dim]")

    # ── Save report ───────────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    output_file = f"swarm_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"# Research Swarm Report\n\n")
        f.write(f"**Query:** {query}\n")
        f.write(f"**Generated:** {timestamp}\n")
        f.write(f"**Time:** {elapsed:.1f}s\n\n")
        f.write("---\n\n")
        f.write(final_report)
        f.write("\n\n---\n\n## Raw Research Findings\n\n")
        f.write(combined_research)
        f.write("\n\n## Analysis\n\n")
        f.write(analyst_result)
        f.write("\n\n## Technical Details\n\n")
        f.write(code_result)

    console.print(f"[dim]Report saved to {output_file}[/dim]\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="🦞 Agent Research Swarm — multi-agent research using local LLMs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python swarm.py                        prompt for a query, use config.yaml models
  python swarm.py "how does X work"      run with this query directly
  python swarm.py --models               list models available in LM Studio
  python swarm.py --pick                 interactively assign models, then prompt for query
  python swarm.py --pick "your query"    pick models, then run with this query
        """
    )
    parser.add_argument("query", nargs="?", default=None, help="Research query (optional)")
    parser.add_argument("--models", action="store_true", help="List available models and exit")
    parser.add_argument("--pick", action="store_true", help="Interactively assign models before running")
    parser.add_argument("--config", default="config.yaml", help="Path to config file (default: config.yaml)")
    args = parser.parse_args()

    config = load_config(args.config)
    server_url = config["server"]["url"]
    api_key = config["server"].get("api_key", "sk-local")
    client = AsyncOpenAI(base_url=server_url, api_key=api_key)

    console.print()
    console.print("[bold cyan]🦞 Agent Research Swarm[/bold cyan]")
    console.print(f"[dim]Server: {server_url}[/dim]\n")

    # --models: just list and exit
    if args.models:
        models = asyncio.run(fetch_available_models(client))
        print_models(models)
        return

    # --pick: interactive model selection
    if args.pick:
        config = asyncio.run(pick_models(config, client))

    # Get query
    query = args.query
    if not query:
        query = console.input("[bold yellow]Research query:[/bold yellow] ").strip()

    if not query:
        console.print("[red]No query provided. Exiting.[/red]")
        return

    asyncio.run(run_swarm(query, config))


if __name__ == "__main__":
    main()
