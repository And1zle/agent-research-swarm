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

# Edit config.yaml — set your LM Studio URL and model assignments
# Then run:
python swarm.py
```

## Usage

```bash
python swarm.py                        # prompt for a query, use config.yaml models
python swarm.py "how does X work"      # pass query directly
python swarm.py --models               # list models available in your server
python swarm.py --pick                 # interactively assign models, then prompt for query
python swarm.py --pick "your query"    # pick models, then run with this query
python swarm.py --config my.yaml       # use a different config file
```

## Configuration

All settings live in `config.yaml`:

```yaml
server:
  url: http://localhost:1234/v1   # LM Studio. Use http://localhost:11434/v1 for Ollama
  api_key: sk-local              # dummy value is fine for local servers

tavily_api_key: ""               # optional — leave blank for offline mode

agents:
  coordinator:
    model: phi-4-mini-instruct   # small + fast
    temperature: 0.3
  researcher:
    model: qwen/qwen3.5-9b
    temperature: 0.6
  analyst:
    model: qwen/qwen3.5-9b
    temperature: 0.2
  summarizer:
    model: qwen/qwen3.5-9b
    temperature: 0.5
  code:
    model: ibm/granite-4-h-tiny
    temperature: 0.1
```

Run `python swarm.py --models` to see what's currently loaded in your server, then update `config.yaml` to match.

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
