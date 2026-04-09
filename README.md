# agent-research-swarm

A local multi-agent research system. Ask it a question and five specialized agents — Coordinator, Researcher, Analyst, Code Agent, and Summarizer — break it down, research it, analyze it, and produce a structured report. Everything runs on your machine via LM Studio or Ollama. No cloud APIs required.

Optionally connects to Tavily for live web search on top of the LLM research.

## How it works

```
Your query
    │
    ▼
Coordinator  →  breaks query into 3-4 focused sub-tasks
    │
    ▼
Researcher   →  tackles each sub-task (+ Tavily web search if enabled)
    │
    ├──────────────────────────┐
    ▼                          ▼
Analyst                    Code Agent     (run in parallel)
    └──────────────────────────┘
                │
                ▼
           Summarizer  →  final report saved to swarm_result_<timestamp>.md
```

Each agent can run a different model. Assign a small fast model to the Coordinator (it only outputs a JSON list) and larger models to the Analyst and Summarizer.

## Quick start

```bash
git clone https://github.com/And1zle/agent-research-swarm
cd agent-research-swarm

pip install -r requirements.txt

# First-time setup — detects LM Studio / Ollama and walks you through model assignment:
python -X utf8 swarm.py setup

# Then run a query:
python -X utf8 swarm.py query "how does X work"
```

> **Windows users:** The `-X utf8` flag ensures correct Unicode rendering in the terminal.

## Commands

```bash
python -X utf8 swarm.py setup                      # First-time setup wizard
python -X utf8 swarm.py status                     # Check server connectivity + current model assignments
python -X utf8 swarm.py query "your question"      # Run a research query
python -X utf8 swarm.py query --pick               # Pick models interactively, then query
python -X utf8 swarm.py query --preset research    # Use a preset template
python -X utf8 swarm.py chat                       # Multi-turn conversation mode
python -X utf8 swarm.py presets                    # List available preset templates
python -X utf8 swarm.py config show                # Show current configuration
python -X utf8 swarm.py config edit                # Edit configuration via wizard
```

## Configuration

On first run, `swarm setup` detects your running server(s) and guides you through assigning models to each agent. Config is saved to `config.yaml` (gitignored — your model assignments and API keys stay local).

To start from a template, copy and edit the example:

```bash
cp config.yaml.example config.yaml
```

Key settings:

```yaml
server:
  url: http://localhost:1234/v1   # LM Studio default. Use http://localhost:11434/v1 for Ollama
  api_key: sk-local              # dummy value is fine for local servers

tavily_api_key: ""               # optional — leave blank for offline mode

agents:
  coordinator:
    model: phi-4-mini-instruct   # small + fast — only outputs a JSON list
    temperature: 0.3
  researcher:
    model: google/gemma-3-12b
    temperature: 0.6
  analyst:
    model: qwen/qwen3.5-9b
    temperature: 0.2
  summarizer:
    model: qwen/qwen3.5-9b
    temperature: 0.5
  code:
    model: ibm-granite/granite-8b-code-instruct-128k
    temperature: 0.1
```

## Preset templates

```bash
python -X utf8 swarm.py query --preset research "what are the latest AI trends?"
python -X utf8 swarm.py query --preset code-review "explain async/await in Python"
python -X utf8 swarm.py query --preset market "opportunities in edge AI"
python -X utf8 swarm.py query --preset debug "why does React re-render so often?"
```

## Web search (optional)

Get a free Tavily API key at [app.tavily.com](https://app.tavily.com) and add it to `config.yaml` under `tavily_api_key`, or set `TAVILY_API_KEY` as an environment variable. When enabled, the Researcher agent gets real web search results for each sub-task before synthesizing.

Without a Tavily key the swarm runs in offline mode — research is based entirely on what the models know.

## Works with any OpenAI-compatible server

- **LM Studio** — `http://localhost:1234/v1`
- **Ollama** — `http://localhost:11434/v1`
- **llamafile** — `http://localhost:8080/v1`

## Requirements

- Python 3.10+
- LM Studio (or Ollama) running with at least one model loaded
- `pip install -r requirements.txt`

## License

MIT — Copyright (c) 2026 Andrew Moya
