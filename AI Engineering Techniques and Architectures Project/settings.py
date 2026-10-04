"""Central configuration. Everything is overridable through environment variables.

No secrets live in the repo: API keys are read from the environment only.
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Load a local .env (gitignored) if present. Real environment variables always win (override=False),
# so tests, the eval runner and Render/CI settings are never overridden by a developer's .env.
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except ImportError:  # python-dotenv is optional
    pass

CORPUS_DIR = Path(os.getenv("CORPUS_DIR", ROOT / "corpus"))
MOCK_DIR = Path(os.getenv("MOCK_DATA_DIR", ROOT / "mock_data"))
RUNTIME_DIR = Path(os.getenv("RUNTIME_DIR", MOCK_DIR / "runtime"))  # mock tickets written here
INDEX_DIR = Path(os.getenv("INDEX_DIR", ROOT / "index"))

# Determinism: every random component (SVD, eval sampling) uses this seed.
SEED = int(os.getenv("SEED", "42"))

# Chunking / retrieval defaults (justified in design-and-evaluation.md, see ablations).
CHUNK_WORDS = int(os.getenv("CHUNK_WORDS", "180"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "40"))
TOP_K = int(os.getenv("TOP_K", "5"))
LSA_DIMS = int(os.getenv("LSA_DIMS", "128"))
# Evidence guardrail: below these the agent refuses / asks instead of answering.
MIN_RELEVANCE = float(os.getenv("MIN_RELEVANCE", "0.22"))
MIN_TERM_COVERAGE = float(os.getenv("MIN_TERM_COVERAGE", "0.6"))

# LLM provider (any OpenAI-compatible endpoint: Groq, OpenRouter, local Ollama...).
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-4o")
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "30"))

# MCP: empty URL -> spawn the server as a stdio subprocess (single-service deployment).
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "")
MCP_CALL_TIMEOUT_S = float(os.getenv("MCP_CALL_TIMEOUT_S", "30"))


def today() -> dt.date:
    """'Today' for all date logic. Set APP_TODAY=YYYY-MM-DD for reproducible demos/evals."""
    raw = os.getenv("APP_TODAY", "").strip()
    if raw:
        return dt.date.fromisoformat(raw)
    return dt.date.today()
