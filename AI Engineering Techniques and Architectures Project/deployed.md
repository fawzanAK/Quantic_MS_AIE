# Deployment

| Item | Value |
|---|---|
| Platform | Render (free web service), config in `render.yaml` |
| Public URL | **TODO - fill in after deploying** (e.g. `https://northwind-hr-agent.onrender.com`) |
| Health check | `<URL>/health` - returns `status: ok` plus a live MCP `search_policy_documents` probe |
| Tool discovery | `<URL>/tools` |
| CI/CD | `.github/workflows/hr-agent-ci.yml` (repo root): tests + evaluation gate -> deploy hook -> `/health` smoke test |
| Last verified | **TODO - date you confirmed `/health` is ok on the deployed URL** |

## Architecture on Render
One web service. The FastAPI app starts, spawns the MCP server as a stdio subprocess, discovers its 8 tools and serves the
UI. `index/` is built during the Render build step (`python -m rag.ingest`).

## Cold start (free tier)
- Idle services sleep; the first request wakes the container (typically tens of seconds, measure it yourself and record it here).
- Local measurements (see `evaluation/results/results.md`): MCP spawn + tool discovery ~1.2-1.5 s, first search ~15 ms, index build ~0.35 s.
- Warm up with `curl <URL>/health` before a demo.

## Secrets
`RENDER_DEPLOY_HOOK_URL`, `APP_URL` (GitHub secrets); `LLM_API_KEY` (Render env var, optional). Nothing else is required.

## Known deployment notes
- Mock tickets are written to local disk (`mock_data/runtime/`), which is ephemeral on Render; this is intentional for a mock.
- This file was written before deployment; no deployed measurement is claimed here.
