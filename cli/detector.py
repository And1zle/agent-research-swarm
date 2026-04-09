"""Auto-detect LM Studio and Ollama servers and their available models."""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

from openai import AsyncOpenAI

KNOWN_SERVERS = [
    {"name": "LM Studio", "url": "http://localhost:1234/v1"},
    {"name": "Ollama",    "url": "http://localhost:11434/v1"},
]

_cache: dict = {"servers": None, "timestamp": 0}
CACHE_TTL = 300  # 5 minutes


@dataclass
class Server:
    name: str
    url: str
    models: list = field(default_factory=list)

    @property
    def available(self) -> bool:
        return len(self.models) > 0


async def _probe_server(name: str, url: str) -> Optional[Server]:
    """Probe a single server and return a Server object if reachable."""
    try:
        client = AsyncOpenAI(base_url=url, api_key="sk-local", timeout=3.0)
        response = await client.models.list()
        models = [m.id for m in response.data]
        return Server(name=name, url=url, models=models)
    except Exception:
        return None


async def detect_servers_async() -> list:
    """Probe all known servers concurrently and return available ones."""
    tasks = [_probe_server(s["name"], s["url"]) for s in KNOWN_SERVERS]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [s for s in results if isinstance(s, Server) and s.available]


def detect_servers(force: bool = False) -> list:
    """Detect available LLM servers. Results cached for 5 minutes."""
    global _cache
    now = time.time()
    if not force and _cache["servers"] is not None and (now - _cache["timestamp"]) < CACHE_TTL:
        return _cache["servers"]
    servers = asyncio.run(detect_servers_async())
    _cache = {"servers": servers, "timestamp": now}
    return servers


def get_all_models(servers: list) -> list:
    """Return flat list of (server_name, model_id) tuples."""
    result = []
    for server in servers:
        for model in server.models:
            result.append((server.name, model))
    return result


def best_server(servers: list) -> Optional[Server]:
    """Return the first available server, preferring LM Studio."""
    for s in servers:
        if s.name == "LM Studio":
            return s
    return servers[0] if servers else None
