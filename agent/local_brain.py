"""
local_brain.py — Local AI inference via Ollama on M4 Pro.

Replaces cloud API calls with on-device models. Each function routes
to the most appropriate local model for its task category:

    Reasoning / decisions : llama3.1:8b
    Creative / drafts     : mistral:7b-instruct
    Code tasks            : deepseek-coder:6.7b
    Quick / routing       : llama3.2
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "30"))

# Model routing table
MODELS = {
    "reason":  os.getenv("LOCAL_MODEL",  "llama3.1:8b"),
    "draft":   os.getenv("DRAFT_MODEL",  "mistral:7b-instruct"),
    "code":    os.getenv("CODER_MODEL",  "deepseek-coder:6.7b"),
    "quick":   os.getenv("QUICK_MODEL",  "llama3.2"),
}

log = logging.getLogger("local_brain")

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _generate(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.7,
    timeout: int = DEFAULT_TIMEOUT,
) -> Optional[str]:
    """Send a prompt to the Ollama /api/generate endpoint.

    Returns the response text, or None on any failure.
    """
    model = model or MODELS["reason"]
    url = f"{OLLAMA_HOST}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except requests.ConnectionError:
        log.error("Ollama unreachable at %s", OLLAMA_HOST)
    except requests.Timeout:
        log.error("Ollama timed out after %ds (model=%s)", timeout, model)
    except requests.RequestException as exc:
        log.error("Ollama request failed: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def think(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.7,
    timeout: int = DEFAULT_TIMEOUT,
) -> Optional[str]:
    """Send a prompt to a local Ollama model and return the response.

    This is the lowest-level public call. All other functions build on it.

    Args:
        prompt:      The full prompt text.
        model:       Ollama model tag. Defaults to llama3.1:8b.
        temperature: Sampling temperature (0.0–1.0).
        timeout:     Request timeout in seconds.

    Returns:
        Model response string, or None on failure.
    """
    return _generate(prompt, model=model, temperature=temperature, timeout=timeout)


def reason(
    objective: str,
    context: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Optional[str]:
    """Higher-level reasoning about an objective.

    Frames the objective with optional context, sends to the reasoning
    model (llama3.1:8b), and returns structured thinking.

    Args:
        objective: What the model should think about.
        context:   Optional background information.
        timeout:   Request timeout in seconds.

    Returns:
        Structured reasoning text, or None on failure.
    """
    parts = [
        "You are a precise reasoning engine. Think step by step.",
        "",
        f"Objective: {objective}",
    ]
    if context:
        parts.insert(2, f"Context:\n{context}\n")
    parts.append(
        "\nProvide your reasoning in clear numbered steps, "
        "then state your conclusion."
    )
    prompt = "\n".join(parts)
    return _generate(
        prompt,
        model=MODELS["reason"],
        temperature=0.3,
        timeout=timeout,
    )


def decide(
    question: str,
    options: List[str],
    context: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Optional[Dict[str, str]]:
    """Pick the best option from a list with reasoning.

    Args:
        question: The decision to make.
        options:  List of option strings.
        context:  Optional background information.
        timeout:  Request timeout in seconds.

    Returns:
        {"choice": "<selected option>", "reasoning": "<why>"} or None.
    """
    option_block = "\n".join(f"  {i+1}. {opt}" for i, opt in enumerate(options))
    parts = [
        "You are a decision engine. Pick the single best option.",
        "",
        f"Question: {question}",
        f"\nOptions:\n{option_block}",
    ]
    if context:
        parts.insert(2, f"Context:\n{context}\n")
    parts.append(
        '\nRespond ONLY with valid JSON: {"choice": "<option text>", "reasoning": "<one sentence>"}'
    )
    prompt = "\n".join(parts)

    raw = _generate(
        prompt,
        model=MODELS["reason"],
        temperature=0.3,
        timeout=timeout,
    )
    if raw is None:
        return None

    # Try to extract JSON from the response.
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Model may wrap JSON in markdown fences — strip them.
        cleaned = raw.strip().strip("`").strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            log.warning("decide() could not parse model output as JSON: %s", raw[:200])
            # Fallback: return raw text as reasoning with first option.
            return {"choice": options[0], "reasoning": raw[:500]}


def analyze(
    data: Any,
    task: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> Optional[str]:
    """Analyze data for a specific task.

    Good for trend analysis, health-check interpretation, metric
    evaluation, or content scoring.

    Args:
        data: Text, JSON-serialisable object, or raw string.
        task: What kind of analysis to perform (e.g. "find trends",
              "score content quality", "check health status").
        timeout: Request timeout in seconds.

    Returns:
        Analysis text, or None on failure.
    """
    if not isinstance(data, str):
        try:
            data_str = json.dumps(data, indent=2, default=str)
        except (TypeError, ValueError):
            data_str = str(data)
    else:
        data_str = data

    prompt = (
        f"You are a data analyst. Perform the following task.\n\n"
        f"Task: {task}\n\n"
        f"Data:\n{data_str}\n\n"
        f"Provide a concise, actionable analysis."
    )
    return _generate(
        prompt,
        model=MODELS["reason"],
        temperature=0.3,
        timeout=timeout,
    )


def draft(
    topic: str,
    style: str = "poetic",
    max_length: int = 280,
    timeout: int = DEFAULT_TIMEOUT,
) -> Optional[str]:
    """Generate a content draft using the creative writing model.

    Uses mistral:7b-instruct, which excels at expressive, stylised text.

    Args:
        topic:      What to write about.
        style:      Tone / style directive (e.g. "poetic", "witty", "technical").
        max_length: Character limit for the output.
        timeout:    Request timeout in seconds.

    Returns:
        Draft text, or None on failure.
    """
    prompt = (
        f"Write a short {style} piece about the following topic.\n\n"
        f"Topic: {topic}\n\n"
        f"Rules:\n"
        f"- Maximum {max_length} characters.\n"
        f"- No hashtags unless they add meaning.\n"
        f"- Be original and memorable.\n"
        f"- Return ONLY the final text, no commentary."
    )
    return _generate(
        prompt,
        model=MODELS["draft"],
        temperature=0.7,
        timeout=timeout,
    )


def code_review(
    code: str,
    task: str = "review",
    timeout: int = DEFAULT_TIMEOUT,
) -> Optional[str]:
    """Review or fix code using the code-specialised model.

    Uses deepseek-coder:6.7b.

    Args:
        code: Source code to review or fix.
        task: What to do — "review", "fix", "explain", "optimize", etc.
        timeout: Request timeout in seconds.

    Returns:
        Review / fix output, or None on failure.
    """
    prompt = (
        f"You are an expert code reviewer.\n\n"
        f"Task: {task}\n\n"
        f"```\n{code}\n```\n\n"
        f"Provide your {task} clearly and concisely."
    )
    return _generate(
        prompt,
        model=MODELS["code"],
        temperature=0.2,
        timeout=timeout,
    )


def quick_think(
    prompt: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> Optional[str]:
    """Fast, lightweight inference for simple decisions.

    Uses llama3.2 (~2 GB) — the fastest local model. Good for routing,
    classification, yes/no questions, and label extraction.

    Args:
        prompt:  The question or instruction.
        timeout: Request timeout in seconds.

    Returns:
        Model response, or None on failure.
    """
    return _generate(
        prompt,
        model=MODELS["quick"],
        temperature=0.3,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def is_available() -> bool:
    """Return True if the Ollama server is reachable."""
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        return r.status_code == 200
    except requests.RequestException:
        return False


def list_models() -> Optional[List[str]]:
    """Return a list of model tags currently available in Ollama.

    Returns None if the server is unreachable.
    """
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        r.raise_for_status()
        models = r.json().get("models", [])
        return [m["name"] for m in models]
    except requests.RequestException as exc:
        log.error("Could not list models: %s", exc)
        return None


def warmup() -> Dict[str, bool]:
    """Pre-load every configured model into memory.

    Sends a trivial prompt to each model so Ollama loads it from disk.
    Returns a dict mapping model name to success boolean.
    """
    results: Dict[str, bool] = {}
    for role, model in MODELS.items():
        log.info("Warming up %s (%s) ...", role, model)
        resp = _generate("Say OK.", model=model, temperature=0.0, timeout=60)
        ok = resp is not None
        results[model] = ok
        status = "ready" if ok else "FAILED"
        log.info("  %s: %s", model, status)
    return results
