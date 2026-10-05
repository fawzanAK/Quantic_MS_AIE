# Deployment

| Item | Value |
|---|---|
| Platform | Render free web service (0.1 CPU, 512 MB), **Docker** runtime using this folder's `Dockerfile` |
| Public URL | **https://northwind-hr-agent-upim.onrender.com** |
| Health check | https://northwind-hr-agent-upim.onrender.com/health - returns `status: ok` plus a live MCP `search_policy_documents` probe |
| Tool discovery | https://northwind-hr-agent-upim.onrender.com/tools |
| CI/CD | `.github/workflows/hr-agent-ci.yml` (repo root): tests + evaluation gate -> deploy hook -> `/health` smoke test |
| LLM | OpenAI `gpt-4o` via OpenRouter (`LLM_API_KEY` set as a Render env var) |
| Last verified | 2026-10-05 - `/health` ok, 8 MCP tools, LLM configured, both demo tasks answered with validated citations |

## Render service settings
Created as a **New Web Service** (not a Blueprint, so it can use the free instance type). `render.yaml` documents the
equivalent Python-runtime configuration.

| Setting | Value |
|---|---|
| Language | Docker |
| Branch | `main` |
| Root Directory | `AI Engineering Techniques and Architectures Project` |
| Dockerfile Path | `AI Engineering Techniques and Architectures Project/Dockerfile` |
| Health Check Path | `/health` |
| Auto-Deploy | Off - GitHub Actions triggers the deploy hook only after tests + the eval gate pass |
| Env vars | `LLM_API_KEY` (secret), `LLM_BASE_URL=https://openrouter.ai/api/v1`, `LLM_MODEL=openai/gpt-4o`, `APP_TODAY=2026-10-01` |

## Architecture on Render
One web service. The FastAPI app starts, spawns the MCP server as a stdio subprocess, discovers its 8 tools and serves the
UI. `index/` is built during the Docker build (`RUN python -m rag.ingest`).

## Measured on the deployed service (2026-10-05)
| Measurement | Value |
|---|---|
| MCP spawn + tool discovery at startup (`mcp_startup_ms`) | ~13.1 s (vs ~1.3-3.5 s locally; free tier has 0.1 CPU) |
| `/health` MCP search probe | ~11 ms |
| First `/chat` after a fresh deploy (one-time warm-up) | ~84 s |
| Warm `/chat` with GPT-4o synthesis | ~2-4 s |
| Warm `/chat` with LLM intent fallback only | ~1-1.5 s |
| Chat UI `/` | ~0.9 s |
| Wake from sleep: first `/health` after idle (2026-10-05) | ~33 s (instance `uptime_s` 18.7 on reply) |
| First `/chat` after waking from sleep | ~3.8 s (no extra warm-up, unlike a fresh deploy) |

## Cold start (free tier)
- Idle free services sleep after ~15 minutes; the next request wakes the container, then the app spawns the MCP subprocess
  (~13 s measured above). Measured wake-from-sleep: the first `/health` after idle took ~33 s end to end.
- Before a demo, open `/health` about a minute ahead. Only right after a fresh deploy is the first chat also slow (~84 s), so
  send one chat message then too.

## Secrets
`RENDER_DEPLOY_HOOK_URL`, `APP_URL` (GitHub Actions secrets); `LLM_API_KEY` (Render env var). Nothing else is required.

## Known deployment notes
- Mock tickets are written to local disk (`mock_data/runtime/`), which is ephemeral on Render; this is intentional for a mock.
