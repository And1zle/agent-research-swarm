"""Core agent pipeline — server connection, agent definitions, and swarm execution."""

import asyncio
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import yaml
from openai import AsyncOpenAI

from cli.visual import (
    console, print_header, print_step, print_success, print_subtasks,
    print_final_report, print_agent_summary, print_debug_block, make_progress
)

# ── Optional Tavily web search ────────────────────────────────────────────────
try:
    from tavily import TavilyClient
    TAVILY_AVAILABLE = True
except ImportError:
    TAVILY_AVAILABLE = False


# ── Config I/O ────────────────────────────────────────────────────────────────

def load_config(path: str = "config.yaml") -> dict:
    config_path = Path(path)
    if not config_path.exists():
        return None
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_config(config: dict, path: str = "config.yaml"):
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def default_config(server_url: str = "http://localhost:1234/v1") -> dict:
    return {
        "server": {"url": server_url, "api_key": "sk-local"},
        "tavily_api_key": "",
        "agents": {
            "coordinator": {"model": "", "temperature": 0.3, "max_tokens": 512},
            "researcher":  {"model": "", "temperature": 0.6, "max_tokens": -1},
            "analyst":     {"model": "", "temperature": 0.2, "max_tokens": -1},
            "summarizer":  {"model": "", "temperature": 0.5, "max_tokens": -1},
            "code":        {"model": "", "temperature": 0.1, "max_tokens": -1},
        },
        "inference": {
            "top_p": 0.95,
            "top_k": 40,
            "repetition_penalty": 1.1,
        },
    }


# ── Agent definitions ─────────────────────────────────────────────────────────

AGENT_META = {
    "coordinator": {
        "emoji": "🎯",
        "role": "Coordinator",
        "system": (
            "You are a research coordinator. Given a research query, break it into "
            "3-4 focused sub-tasks for specialized agents.\n"
            "IMPORTANT: Return ONLY a valid JSON array of plain strings. "
            "Each element must be a string, NOT an object or dict.\n"
            'WRONG:   [{"task": "Find statistics"}, {"task": "Analyze trends"}]\n'
            'CORRECT: ["Find statistics", "Analyze trends", "Summarize findings"]\n'
            "Output nothing except the JSON array."
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


def build_agents(config: dict) -> dict:
    agents = {}
    for key, meta in AGENT_META.items():
        agent_cfg = config.get("agents", {}).get(key, {})
        # If a preset injected a custom system prompt, use it
        system = agent_cfg.get("system", meta["system"])
        agents[key] = {
            **meta,
            "system":      system,
            "model":       agent_cfg.get("model", ""),
            "temperature": agent_cfg.get("temperature", 0.5),
            "max_tokens":  agent_cfg.get("max_tokens", 800),
        }
    return agents


# ── Utilities ─────────────────────────────────────────────────────────────────

def strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks (DeepSeek R1 etc.)."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def parse_subtasks(coordinator_output: str) -> list:
    def _normalize(item) -> str | None:
        """Accept a plain string, or extract the first long string value from a dict."""
        if isinstance(item, str) and len(item) > 5:
            return item
        if isinstance(item, dict):
            for v in item.values():
                if isinstance(v, str) and len(v) > 5:
                    return v
        return None

    try:
        start = coordinator_output.find("[")
        end   = coordinator_output.rfind("]") + 1
        if start != -1 and end > start:
            parsed = json.loads(coordinator_output[start:end])
            if isinstance(parsed, list):
                result = [s for s in (_normalize(x) for x in parsed) if s]
                if result:
                    return result[:4]
    except Exception:
        pass
    lines = [l.strip().lstrip("0123456789.-) ") for l in coordinator_output.split("\n") if l.strip()]
    return [l for l in lines if len(l) > 10][:4]


# ── Web search ────────────────────────────────────────────────────────────────

async def search_web(tavily, query: str, max_results: int = 8) -> str:
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

# Params supported by OpenAI-compatible APIs (LM Studio, Ollama)
_SUPPORTED_PARAMS = {"top_p", "presence_penalty", "frequency_penalty", "stop", "seed"}


async def call_agent(
    client: AsyncOpenAI,
    agent: dict,
    prompt: str,
    inference_params: dict,
    debug: bool = False,
) -> str:
    params = {
        k: v for k, v in inference_params.items()
        if k in _SUPPORTED_PARAMS and v is not None
    }
    try:
        max_tok = agent["max_tokens"]
        create_kwargs = dict(
            model=agent["model"],
            messages=[
                {"role": "system", "content": agent["system"]},
                {"role": "user",   "content": prompt},
            ],
            temperature=agent["temperature"],
            **params,
        )
        if max_tok and max_tok > 0:
            create_kwargs["max_tokens"] = max_tok
        response = await client.chat.completions.create(**create_kwargs)
        raw = response.choices[0].message.content.strip()
        if debug:
            print_debug_block(f"{agent['role']} raw output", raw)
        return strip_think_tags(raw)
    except Exception as e:
        return f"[Agent error: {e}]"


# ── Main swarm pipeline ───────────────────────────────────────────────────────

async def run_swarm(query: str, config: dict, debug: bool = False, context: str = ""):
    """
    Run the full multi-agent research pipeline.

    Args:
        query:   The research question.
        config:  Loaded (and optionally preset-patched) config dict.
        debug:   If True, show raw agent outputs including <think> tags.
        context: Optional prior conversation context (for chat mode).

    Returns:
        final_report (str)
    """
    server_url       = config["server"]["url"]
    api_key          = config["server"].get("api_key", "sk-local")
    tavily_key       = config.get("tavily_api_key", "") or os.environ.get("TAVILY_API_KEY", "")
    inference_params = config.get("inference", {})
    agents           = build_agents(config)

    client = AsyncOpenAI(base_url=server_url, api_key=api_key)
    tavily = TavilyClient(api_key=tavily_key) if (TAVILY_AVAILABLE and tavily_key) else None
    web_search_enabled = tavily is not None

    timings: dict = {}
    start_time = time.time()

    print_header(query, server_url, web_search_enabled)

    # ── Step 1: Coordinator ───────────────────────────────────────────────
    print_step(1, 4, agents["coordinator"]["emoji"], "Coordinator", agents["coordinator"]["model"],
               "breaking down query...")
    t0 = time.time()
    with console.status("[cyan]Coordinator thinking...[/cyan]"):
        coord_prompt = f"Research query: {query}\nBreak this into 3-4 focused sub-tasks."
        if context:
            coord_prompt = f"Prior context:\n{context}\n\n{coord_prompt}"
        coordinator_output = await call_agent(
            client, agents["coordinator"], coord_prompt, inference_params, debug
        )
    timings["coordinator"] = time.time() - t0

    subtasks = parse_subtasks(coordinator_output) or [query]
    print_success(f"{len(subtasks)} sub-tasks identified:")
    print_subtasks(subtasks)

    # ── Step 2: Research ──────────────────────────────────────────────────
    if web_search_enabled:
        print_step(2, 4, "🌐", f"Web Search + {agents['researcher']['emoji']} Researcher",
                   agents["researcher"]["model"])
    else:
        print_step(2, 4, agents["researcher"]["emoji"], "Researcher",
                   agents["researcher"]["model"])

    research_findings = []
    t0 = time.time()
    for i, task in enumerate(subtasks, 1):
        if web_search_enabled:
            with console.status(f"[cyan]Searching + synthesizing sub-task {i}/{len(subtasks)}...[/cyan]"):
                t_ws = time.time()
                search_result = await search_web(tavily, task)
                timings["web_search"] = timings.get("web_search", 0) + (time.time() - t_ws)
                finding = await call_agent(
                    client, agents["researcher"],
                    f"Sub-task: {task}\n\nWeb results:\n{search_result}\n\nSynthesize findings.",
                    inference_params, debug
                )
        else:
            with console.status(f"[cyan]Researching sub-task {i}/{len(subtasks)}...[/cyan]"):
                finding = await call_agent(
                    client, agents["researcher"],
                    f"Sub-task: {task}\n\nProvide thorough findings.",
                    inference_params, debug
                )
        research_findings.append(f"### Sub-task {i}: {task}\n{finding}")
        print_success(f"Sub-task {i}/{len(subtasks)} complete ({len(finding)} chars)")
    timings["researcher"] = time.time() - t0
    console.print()

    combined_research = "\n\n".join(research_findings)

    # ── Step 3: Analyst + Code Agent (parallel) ───────────────────────────
    print_step(3, 4,
               f"{agents['analyst']['emoji']}+{agents['code']['emoji']}",
               f"Analyst + Code Agent",
               f"{agents['analyst']['model']} · {agents['code']['model']}",
               "(parallel)")

    analyst_prompt = (
        f"Original query: {query}\n\nResearch findings:\n{combined_research}\n\n"
        f"Identify key patterns, insights, and implications."
    )
    code_prompt = (
        f"Original query: {query}\n\nResearch findings:\n{combined_research}\n\n"
        f"Provide relevant code examples or technical details if applicable."
    )

    t0 = time.time()
    with console.status("[cyan]Analyst & Code Agent working in parallel...[/cyan]"):
        analyst_result, code_result = await asyncio.gather(
            call_agent(client, agents["analyst"], analyst_prompt, inference_params, debug),
            call_agent(client, agents["code"],    code_prompt,    inference_params, debug),
        )
    elapsed_parallel = time.time() - t0
    timings["analyst"] = elapsed_parallel / 2
    timings["code"]    = elapsed_parallel / 2

    print_success(f"Analysis complete ({len(analyst_result)} chars)")
    print_success(f"Code agent complete ({len(code_result)} chars)")
    console.print()

    # ── Step 4: Summarizer ────────────────────────────────────────────────
    print_step(4, 4, agents["summarizer"]["emoji"], "Summarizer",
               agents["summarizer"]["model"], "writing final report...")

    summary_prompt = (
        f"Original research query: {query}\n\n"
        f"## Research Findings\n{combined_research}\n\n"
        f"## Analysis\n{analyst_result}\n\n"
        f"## Technical Details\n{code_result}\n\n"
        "Write a comprehensive, well-structured final report in markdown."
    )

    t0 = time.time()
    with console.status("[cyan]Summarizer writing report...[/cyan]"):
        final_report = await call_agent(
            client, agents["summarizer"], summary_prompt, inference_params, debug
        )
    timings["summarizer"] = time.time() - t0

    elapsed = time.time() - start_time

    # ── Display & Save ────────────────────────────────────────────────────
    print_final_report(final_report, elapsed)
    print_agent_summary(agents, web_search_enabled, timings, elapsed)

    output_file = f"swarm_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    timestamp   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"# Research Swarm Report\n\n")
        f.write(f"**Query:** {query}\n**Generated:** {timestamp}\n**Time:** {elapsed:.1f}s\n\n---\n\n")
        f.write(final_report)
        f.write(f"\n\n---\n\n## Raw Research Findings\n\n{combined_research}")
        f.write(f"\n\n## Analysis\n\n{analyst_result}")
        f.write(f"\n\n## Technical Details\n\n{code_result}")

    console.print(f"[dim]Report saved → {output_file}[/dim]\n")

    return final_report
