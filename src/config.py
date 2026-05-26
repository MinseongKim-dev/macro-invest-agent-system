"""LLM provider + CORS configuration.

ENV_MODE=PRODUCTION  → Groq API (external, zero VPS RAM).
ENV_MODE=LOCAL       → Groq if GROQ_API_KEY set, else ChatOllama.

Tri-File exception: this file is introduced for v0.2.0 production
architecture only because main.py grew a dual-provider LLM path that
would otherwise pollute its startup logic.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ── Environment ───────────────────────────────────────────────────────────────

ENV_MODE     = os.environ.get("ENV_MODE", "LOCAL").upper()   # LOCAL | PRODUCTION
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL   = os.environ.get("GROQ_MODEL", "llama3-70b-8192")
OLLAMA_URL   = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")

IS_PRODUCTION = ENV_MODE == "PRODUCTION"

# ── CORS ─────────────────────────────────────────────────────────────────────

# Base origins always allowed (local dev + Docker compose frontend)
CORS_ORIGINS: list[str] = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:8001",
]

# Runtime injection — comma-separated list via env var
# e.g. CORS_ALLOWED_ORIGINS=https://aleph-one.vercel.app,https://custom.domain.com
_extra_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "")
if _extra_origins:
    CORS_ORIGINS.extend(o.strip() for o in _extra_origins.split(",") if o.strip())


# ── LLM factory ──────────────────────────────────────────────────────────────

def get_llm() -> Any:  # noqa: ANN401
    """Return the configured LLM instance.

    PRODUCTION mode forces Groq (requires GROQ_API_KEY).
    LOCAL mode uses Groq when GROQ_API_KEY is present, falls back to Ollama.
    Raises RuntimeError if no provider is available (caught upstream).
    """
    if IS_PRODUCTION:
        if not GROQ_API_KEY:
            raise RuntimeError(
                "GROQ_API_KEY must be set when ENV_MODE=PRODUCTION. "
                "Obtain a free key at https://console.groq.com"
            )
        try:
            from langchain_groq import ChatGroq
        except ImportError as exc:
            raise RuntimeError("langchain-groq not installed") from exc
        logger.info("llm_provider", extra={"provider": "groq_production", "model": GROQ_MODEL})
        return ChatGroq(model=GROQ_MODEL, temperature=0.1, api_key=GROQ_API_KEY)

    # LOCAL: Groq preferred when key present
    if GROQ_API_KEY:
        try:
            from langchain_groq import ChatGroq
            logger.info("llm_provider", extra={"provider": "groq_local", "model": GROQ_MODEL})
            return ChatGroq(model=GROQ_MODEL, temperature=0.1)
        except ImportError:
            logger.warning("langchain_groq_missing_fallback_ollama")

    # LOCAL fallback: Ollama
    try:
        from langchain_ollama import ChatOllama
        logger.info("llm_provider", extra={"provider": "ollama", "model": OLLAMA_MODEL})
        return ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_URL)
    except ImportError as exc:
        raise RuntimeError(
            "No LLM available. Install langchain-groq (set GROQ_API_KEY) "
            "or langchain-ollama (with Ollama running locally)."
        ) from exc
