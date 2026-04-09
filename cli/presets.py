"""Preset templates for common research types."""

import copy

PRESETS = {
    "research": {
        "name": "General Research",
        "emoji": "🔬",
        "description": "Deep research with comprehensive multi-source report",
        "agent_overrides": {
            "researcher":  {"temperature": 0.5, "max_tokens": 1000},
            "analyst":     {"temperature": 0.2},
            "summarizer":  {"temperature": 0.4, "max_tokens": 1500},
        },
    },
    "code-review": {
        "name": "Code Review",
        "emoji": "💻",
        "description": "Technical analysis, patterns, bugs, and improvement suggestions",
        "agent_overrides": {
            "coordinator": {
                "temperature": 0.2,
                "system": (
                    "You are a technical lead. Break this code review request into "
                    "3-4 specific areas: architecture, patterns, bugs, improvements. "
                    "Return ONLY a JSON array of strings."
                ),
            },
            "researcher": {
                "temperature": 0.3,
                "system": (
                    "You are a senior software engineer. Analyze the given code or technical "
                    "topic. Focus on correctness, patterns, and best practices."
                ),
            },
            "code": {"temperature": 0.1, "max_tokens": 1500},
        },
    },
    "market": {
        "name": "Market Analysis",
        "emoji": "📈",
        "description": "Market trends, competitive landscape, and business opportunities",
        "agent_overrides": {
            "researcher": {
                "temperature": 0.4,
                "system": (
                    "You are a market research specialist. Provide data-driven findings "
                    "on market trends, competitive landscape, and business opportunities."
                ),
            },
            "analyst": {
                "temperature": 0.2,
                "system": (
                    "You are a business analyst. Identify market opportunities, threats, "
                    "key trends, and strategic insights from the research provided."
                ),
            },
            "summarizer": {"max_tokens": 1500},
        },
    },
    "debug": {
        "name": "Debug Investigation",
        "emoji": "🐛",
        "description": "Root cause analysis and fix suggestions for technical issues",
        "agent_overrides": {
            "coordinator": {
                "temperature": 0.1,
                "system": (
                    "You are a debugging expert. Break this issue into: "
                    "1) Reproduce the issue, 2) Identify root cause, "
                    "3) Find similar patterns, 4) Suggest fixes. "
                    "Return ONLY a JSON array of strings."
                ),
            },
            "analyst": {
                "temperature": 0.1,
                "system": (
                    "You are a root cause analyst. Identify the exact cause of the issue, "
                    "contributing factors, and the chain of events that led to it."
                ),
            },
            "code": {"temperature": 0.1, "max_tokens": 1500},
        },
    },
}


def list_presets() -> dict:
    return PRESETS


def get_preset(name: str) -> dict | None:
    return PRESETS.get(name)


def apply_preset(config: dict, preset_name: str) -> dict:
    """Deep-merge a preset's agent overrides into config."""
    preset = PRESETS.get(preset_name)
    if not preset:
        return config
    config = copy.deepcopy(config)
    for agent_key, overrides in preset.get("agent_overrides", {}).items():
        config.setdefault("agents", {}).setdefault(agent_key, {}).update(overrides)
    return config
