# Northwind HR Assistant - agentic RAG + MCP

An agentic HR assistant for the **fictional** company Northwind Analytics (offices in Austin, Karachi and London). It answers
HR policy questions with cited evidence and carries out multi-step HR tasks (PTO requests, remote-work eligibility, expense
checks, HR-case triage) by calling tools **through a Model Context Protocol (MCP) server**. All data is synthetic.

| Piece | Where |
|---|---|
| Policy corpus (17 docs, md/html/txt, ~12.6k words ~ 31 pages) | `corpus/` |
| Mock structured data (employees, PTO, benefits, tickets) | `mock_data/` |
| RAG (parsing, chunking, TF-IDF+LSA+FAISS hybrid index) | `rag/` |
| MCP server (8 tools, stdio + streamable-HTTP) | `mcp_server/` |
| Agent, MCP client, web app + chat UI | `app/` |
| Evaluation (30 questions, runner, results) | `evaluation/` |
| Tests (48) and CI/CD | `tests/`, `.github/workflows/hr-agent-ci.yml` (at the repo root) |
| Docs | `design-and-evaluation.md`, `ai-tooling.md`, `deployed.md` |

> The server package is called `mcp_server/` (not `mcp/`) so it never shadows the official `mcp` SDK.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate        # Python 3.12+
pip install -r requirements-dev.txt
cp .env.example .env                                     # then fill in LLM_API_KEY (optional)
python -m rag.ingest                                     # builds index/ (also built automatically if missing)
APP_TODAY=2026-10-01 uvicorn app.main:app --reload       # http://localhost:8000
```

`APP_TODAY` freezes "today" so demos and the evaluation are reproducible (reference date 2026-10-01, a Thursday).
Leave it unset to use the real date. An LLM key is **optional** (see below).

By default the app spawns the MCP server as a stdio subprocess (one free-tier service). To run the MCP server separately:

```bash
python -m mcp_server.server --transport streamable-http --port 8001
MCP_SERVER_URL=http://localhost:8001/mcp uvicorn app.main:app
```

### Endpoints
`GET /health` (live MCP probe) - `POST /chat` - `POST /confirm` / `POST /cancel` (mock ticket approval) - `GET /tools`
(MCP tool discovery) - `GET /employees` - `GET /demo-tasks` - `GET /` (chat UI with visible tool-call trace).

### Try the two demo tasks (pick the employee in the UI, or use the demo buttons)
1. **E1001 Amina** - "Can I take 3 days of PTO next week?"
2. **E1004 Liam** - "Can I work remotely from Spain for six weeks starting November 16?"

## Optional LLM
Set `LLM_API_KEY` in `.env` (loaded automatically; real env vars take precedence) or in the environment. Any
OpenAI-compatible endpoint works; `.env.example` and `render.yaml` are set up for OpenRouter (key from
https://openrouter.ai/keys), with Groq as a commented alternative. The LLM only
(a) classifies low-confidence intents and (b) polishes the final wording. Polished answers are validated - every citation must
have been retrieved and every number must appear in the evidence - otherwise the deterministic answer is kept.
**The LLM path has only been tested with a mock transport, never against a live provider** (see `design-and-evaluation.md`).

## Tests and evaluation
```bash
python -m pytest -q                      # 48 tests incl. MCP tool discovery + real tool calls over stdio
python -m evaluation.run_eval            # full run: metrics, latency, ablations -> evaluation/results/
python -m evaluation.run_eval --quick    # CI gate: main metrics only, non-zero exit below thresholds
```

## Deploy (Render free tier)
1. Push to GitHub, create a Render **Blueprint** from the repo and set the Blueprint path to
   `AI Engineering Techniques and Architectures Project/render.yaml` (it sets `rootDir` to this subfolder), or create a
   Web Service with the same commands and Root Directory set to this folder.
2. Render env vars: `APP_TODAY` (optional), `LLM_API_KEY` (optional).
3. In Render, copy the service's **Deploy Hook URL**. In GitHub -> Settings -> Secrets add `RENDER_DEPLOY_HOOK_URL` and `APP_URL`
   (the public https URL).
4. Push to `main`: CI runs tests + the evaluation gate; only if they pass does the `deploy` job call the hook and poll `/health`.
5. Put the URL into `deployed.md`.

**Free-tier cold start:** Render sleeps idle free services; the first request after idle can take ~30-60 s while the container
wakes, then the app spawns the MCP subprocess (~1.3 s locally) and loads the index. Open `/health` before a demo to warm it.

## Safety model (short)
Retrieval-evidence guardrail (refuses instead of guessing) - the agent can only preview tickets (`confirmed=false`);
only the human-triggered `/confirm` writes, once, within 30 minutes - emails are drafts, never sent - citations are validated
against retrieved text - HR-sensitive cases are routed to humans, not judged.
