"""LM Studio management API — load models with optimal settings via /api/v0."""

import time

import httpx

from cli.profiles import ModelProfile, get_profile
from cli.visual import console


# ── URL helpers ────────────────────────────────────────────────────────────────

def _derive_mgmt_url(openai_url: str) -> str:
    """Convert an OpenAI-compat URL to the LM Studio management API base URL.

    http://localhost:1234/v1  →  http://localhost:1234/api/v0
    """
    url = openai_url.rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    return url.rstrip("/") + "/api/v0"


# ── Connectivity probe ─────────────────────────────────────────────────────────

def _is_management_api_available(mgmt_url: str) -> bool:
    """Return True if the LM Studio management API responds (LM Studio ≥ 0.3.6 required)."""
    try:
        r = httpx.get(f"{mgmt_url}/models", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


def is_management_api_available(openai_url: str) -> bool:
    """Public helper — check from an OpenAI-compat URL."""
    return _is_management_api_available(_derive_mgmt_url(openai_url))


# ── Model listing ──────────────────────────────────────────────────────────────

def get_loaded_models(openai_url: str) -> list[str] | None:
    """Return a list of currently loaded model identifiers, or None if API unavailable."""
    mgmt_url = _derive_mgmt_url(openai_url)
    if not _is_management_api_available(mgmt_url):
        return None
    try:
        r = httpx.get(f"{mgmt_url}/models", timeout=5.0)
        r.raise_for_status()
        data = r.json()
        models = data if isinstance(data, list) else data.get("data", [])
        return [m.get("id") or m.get("identifier", "") for m in models if isinstance(m, dict)]
    except Exception:
        return None


# ── Model loading ──────────────────────────────────────────────────────────────

def load_model(openai_url: str, model_id: str, profile: ModelProfile | None = None) -> bool:
    """POST to LM Studio /api/v0/models/load with optimal profile settings.

    Returns True if the model is confirmed loaded, False otherwise.
    Blocks until the model state == "loaded" (up to 120 s).
    """
    mgmt_url = _derive_mgmt_url(openai_url)
    if not _is_management_api_available(mgmt_url):
        return False

    if profile is None:
        profile = get_profile(model_id)

    payload = {
        "identifier": model_id,
        "config": {
            "gpuOffload": {"ratio": profile.gpu_offload_ratio},
            "contextLength": profile.context_length,
            "maxConcurrentPredictions": 1,      # hardcoded — one user, one task
            "kvCacheQuantizationType": "Q4_0",  # saves VRAM with minimal quality loss
        },
    }

    try:
        r = httpx.post(f"{mgmt_url}/models/load", json=payload, timeout=15.0)
        if r.status_code not in (200, 201, 202):
            console.print(
                f"[yellow]  Load request returned {r.status_code}: {r.text[:120]}[/yellow]"
            )
            return False
    except Exception as e:
        console.print(f"[yellow]  Load request failed: {e}[/yellow]")
        return False

    return _wait_for_model_ready(mgmt_url, model_id)


# ── Readiness polling ──────────────────────────────────────────────────────────

def _wait_for_model_ready(mgmt_url: str, model_id: str, timeout: int = 120) -> bool:
    """Poll GET /api/v0/models until model_id has state == 'loaded'.

    Shows a spinner and elapsed time. Returns True on success, False on timeout.
    """
    deadline = time.time() + timeout
    model_id_lower = model_id.lower()

    with console.status(f"[cyan]Loading {model_id} — waiting for ready...[/cyan]") as status:
        while time.time() < deadline:
            try:
                r = httpx.get(f"{mgmt_url}/models", timeout=5.0)
                if r.status_code == 200:
                    data = r.json()
                    models = data if isinstance(data, list) else data.get("data", [])
                    for m in models:
                        m_id = (m.get("id") or m.get("identifier", "")).lower()
                        m_state = m.get("state", "")
                        if model_id_lower in m_id or m_id in model_id_lower:
                            if m_state == "loaded":
                                elapsed = timeout - (deadline - time.time())
                                status.update(
                                    f"[green]{model_id} ready ({elapsed:.0f}s)[/green]"
                                )
                                return True
                            elif m_state in ("loading", "queued"):
                                elapsed = timeout - (deadline - time.time())
                                status.update(
                                    f"[cyan]Loading {model_id} — {m_state} "
                                    f"({elapsed:.0f}s elapsed)...[/cyan]"
                                )
            except Exception:
                pass
            time.sleep(2)

    console.print(f"[yellow]  Timed out waiting for {model_id} to load.[/yellow]")
    return False
