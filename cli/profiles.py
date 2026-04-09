"""Model profile database — GPU offload, context length, quantization recommendations."""

from dataclasses import dataclass, field


@dataclass
class ModelProfile:
    name: str
    gpu_offload_ratio: float        # 0.0–1.0 (fraction of layers to offload to GPU)
    context_length: int             # recommended context window
    quant_recommendation: str       # Q4_K_M, Q5_K_M, Q8_0, IQ3_M, F16
    quant_note: str = ""            # human-readable explanation
    max_concurrent_predictions: int = 1   # always 1 for single-user local inference
    kv_cache_quant_type: str = "Q4_0"     # KV cache quantization — Q4_0 saves VRAM
    patterns: list[str] = field(default_factory=list)  # substrings to match against model IDs


# ── Profile registry ───────────────────────────────────────────────────────────
# Patterns are matched case-insensitively as substrings of the model ID.
# First matching profile wins. Default catches everything else.

_PROFILES: list[ModelProfile] = [

    # ── Phi ──────────────────────────────────────────────────────────────────
    ModelProfile(
        name="Phi-4 Mini",
        gpu_offload_ratio=0.90,
        context_length=16384,
        quant_recommendation="Q4_K_M",
        quant_note="Small model, fits mostly on GPU at Q4_K_M",
        patterns=["phi-4-mini", "phi4-mini"],
    ),
    ModelProfile(
        name="Phi-4",
        gpu_offload_ratio=0.85,
        context_length=16384,
        quant_recommendation="Q4_K_M",
        quant_note="14B model — Q4_K_M keeps VRAM use manageable",
        patterns=["phi-4", "phi4"],
    ),
    ModelProfile(
        name="Phi-3",
        gpu_offload_ratio=0.90,
        context_length=4096,
        quant_recommendation="Q4_K_M",
        quant_note="Older Phi, shorter context window",
        patterns=["phi-3", "phi3"],
    ),

    # ── Qwen ─────────────────────────────────────────────────────────────────
    ModelProfile(
        name="Qwen 3.5 35B / Qwen 3 30B",
        gpu_offload_ratio=0.40,
        context_length=8192,
        quant_recommendation="IQ3_M",
        quant_note="Large MoE — IQ3_M is the sweet spot for VRAM vs quality",
        patterns=["qwen3.5-35b", "qwen3-35b", "qwen3.5-30b", "qwen3-30b", "qwen/qwen3.5-35b", "qwen/qwen3-30b"],
    ),
    ModelProfile(
        name="Qwen 3.5 9B / Qwen 3 9B",
        gpu_offload_ratio=0.85,
        context_length=8192,
        quant_recommendation="Q4_K_M",
        quant_note="Mid-size, fits well at Q4_K_M",
        patterns=["qwen3.5-9b", "qwen3-9b", "qwen/qwen3.5-9b", "qwen/qwen3-9b"],
    ),
    ModelProfile(
        name="Qwen 3.5 7B / Qwen 3 7B",
        gpu_offload_ratio=0.90,
        context_length=8192,
        quant_recommendation="Q4_K_M",
        quant_note="Compact, mostly fits on GPU",
        patterns=["qwen3.5-7b", "qwen3-7b"],
    ),

    # ── Gemma ─────────────────────────────────────────────────────────────────
    ModelProfile(
        name="Gemma 4 27B / 26B",
        gpu_offload_ratio=0.50,
        context_length=8192,
        quant_recommendation="Q4_K_M",
        quant_note="Large model — 50% GPU offload recommended to avoid OOM",
        patterns=["gemma-4-27b", "gemma-4-26b", "gemma4-27b", "gemma4-26b", "google/gemma-4"],
    ),
    ModelProfile(
        name="Gemma 3 12B",
        gpu_offload_ratio=0.75,
        context_length=8192,
        quant_recommendation="Q4_K_M",
        quant_note="Good mid-size model, 75% GPU offload fits most setups",
        patterns=["gemma-3-12b", "gemma3-12b", "google/gemma-3-12b"],
    ),
    ModelProfile(
        name="Gemma 3 4B",
        gpu_offload_ratio=0.95,
        context_length=8192,
        quant_recommendation="Q4_K_M",
        quant_note="Small model, almost fully on GPU",
        patterns=["gemma-3-4b", "gemma3-4b", "google/gemma-3-4b"],
    ),
    ModelProfile(
        name="Gemma 3 1B",
        gpu_offload_ratio=0.99,
        context_length=4096,
        quant_recommendation="Q4_K_M",
        quant_note="Tiny model, fully on GPU",
        patterns=["gemma-3-1b", "gemma3-1b"],
    ),

    # ── IBM Granite ───────────────────────────────────────────────────────────
    ModelProfile(
        name="Granite 8B Code",
        gpu_offload_ratio=0.85,
        context_length=8192,
        quant_recommendation="Q4_K_M",
        quant_note="Code-specialized 8B — high GPU offload for fast generation",
        patterns=["granite-8b-code", "granite-8b", "ibm-granite/granite-8b", "ibm/granite-8b",
                  "ibm-granite.granite-8b"],
    ),
    ModelProfile(
        name="Granite 4 H Tiny",
        gpu_offload_ratio=0.95,
        context_length=4096,
        quant_recommendation="Q4_K_M",
        quant_note="Very small, runs almost entirely on GPU",
        patterns=["granite-4-h-tiny", "granite4-h-tiny", "ibm/granite-4-h", "ibm-granite/granite-4"],
    ),
    ModelProfile(
        name="Granite 3.3 8B",
        gpu_offload_ratio=0.85,
        context_length=8192,
        quant_recommendation="Q4_K_M",
        quant_note="Latest Granite 8B",
        patterns=["granite-3.3-8b", "granite3.3-8b", "ibm-granite/granite-3.3"],
    ),

    # ── Liquid / LFM ─────────────────────────────────────────────────────────
    ModelProfile(
        name="Liquid LFM2 24B",
        gpu_offload_ratio=0.55,
        context_length=8192,
        quant_recommendation="Q4_K_M",
        quant_note="24B hybrid model — 55% offload balances quality vs VRAM",
        patterns=["lfm2-24b", "lfm-2-24b", "liquid/lfm2", "liquid/lfm-2"],
    ),

    # ── DeepSeek ──────────────────────────────────────────────────────────────
    ModelProfile(
        name="DeepSeek R1 0528",
        gpu_offload_ratio=0.80,
        context_length=8192,
        quant_recommendation="Q4_K_M",
        quant_note="Reasoning model — note: outputs <think> blocks (auto-stripped)",
        patterns=["deepseek-r1-0528", "deepseek-r1"],
    ),
    ModelProfile(
        name="DeepSeek Coder V2 Lite",
        gpu_offload_ratio=0.85,
        context_length=8192,
        quant_recommendation="Q4_K_M",
        quant_note="Code-focused, MoE lite variant",
        patterns=["deepseek-coder-v2-lite", "deepseek-coder"],
    ),

    # ── NVIDIA Nemotron ───────────────────────────────────────────────────────
    ModelProfile(
        name="Nemotron 3 Nano",
        gpu_offload_ratio=0.95,
        context_length=4096,
        quant_recommendation="Q4_K_M",
        quant_note="Tiny model — fully on GPU",
        patterns=["nemotron-3-nano", "nemotron-nano", "nvidia/nemotron"],
    ),

    # ── Mistral / Ministral ───────────────────────────────────────────────────
    ModelProfile(
        name="Ministral 3B / Mistral 3B",
        gpu_offload_ratio=0.95,
        context_length=4096,
        quant_recommendation="Q4_K_M",
        quant_note="Very small, fully on GPU",
        patterns=["ministral-3b", "mistral-3b", "ministral-3", "mistral/ministral"],
    ),
    ModelProfile(
        name="Mistral 7B",
        gpu_offload_ratio=0.90,
        context_length=4096,
        quant_recommendation="Q4_K_M",
        quant_note="Classic 7B, mostly on GPU at Q4_K_M",
        patterns=["mistral-7b", "mistral-0."],
    ),

    # ── LLaMA ─────────────────────────────────────────────────────────────────
    ModelProfile(
        name="LLaMA 3.2 1B",
        gpu_offload_ratio=0.99,
        context_length=4096,
        quant_recommendation="Q4_K_M",
        quant_note="Tiny, fully on GPU",
        patterns=["llama-3.2-1b", "llama3.2-1b"],
    ),
    ModelProfile(
        name="LLaMA 3.2 3B",
        gpu_offload_ratio=0.98,
        context_length=4096,
        quant_recommendation="Q4_K_M",
        quant_note="Very small, fully on GPU",
        patterns=["llama-3.2-3b", "llama3.2-3b"],
    ),
    ModelProfile(
        name="LLaMA 3.1 8B",
        gpu_offload_ratio=0.87,
        context_length=8192,
        quant_recommendation="Q4_K_M",
        quant_note="Strong 8B, high GPU offload",
        patterns=["llama-3.1-8b", "llama3.1-8b", "meta-llama/llama-3.1-8b"],
    ),
    ModelProfile(
        name="LLaMA 3 8B",
        gpu_offload_ratio=0.87,
        context_length=8192,
        quant_recommendation="Q4_K_M",
        quant_note="Classic LLaMA 3 8B",
        patterns=["llama-3-8b", "llama3-8b", "meta-llama/meta-llama-3-8b"],
    ),
]

# Default profile for any model not matched above
_DEFAULT_PROFILE = ModelProfile(
    name="Unknown Model",
    gpu_offload_ratio=0.80,
    context_length=4096,
    quant_recommendation="Q4_K_M",
    quant_note="Unknown model — using conservative defaults",
    patterns=[],
)


# ── Public API ─────────────────────────────────────────────────────────────────

def get_profile(model_id: str) -> ModelProfile:
    """Return the best matching ModelProfile for a model ID. Always returns a valid profile."""
    model_lower = model_id.lower()
    for profile in _PROFILES:
        for pattern in profile.patterns:
            if pattern.lower() in model_lower:
                return profile
    return _DEFAULT_PROFILE


def is_known_model(model_id: str) -> bool:
    """Return True if model_id matches a named profile (not the default)."""
    model_lower = model_id.lower()
    for profile in _PROFILES:
        for pattern in profile.patterns:
            if pattern.lower() in model_lower:
                return True
    return False
