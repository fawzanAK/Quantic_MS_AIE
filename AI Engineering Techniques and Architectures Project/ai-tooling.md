# AI tooling used

## Tools
- **Claude (Anthropic) via Claude Code** wrote the large majority of the code, the synthetic corpus and mock data, the tests,
  the evaluation harness, CI configuration and these documents, working from the project brief.
- **No AI-generated runtime dependencies are required.** At runtime the app can optionally call an OpenAI-compatible LLM
  (OpenAI GPT-4o via OpenRouter by default); it is off unless `LLM_API_KEY` is set. All reported evaluation numbers were produced with it OFF.

## How AI was used
| Area | AI contribution | Human responsibility |
|---|---|---|
| Corpus / mock data | Generated the 17 fictional policies and 15 synthetic employees | Review for realism; replace if desired |
| Code | Generated RAG, MCP server, agent, UI, tests | Read, run and understand the code before submitting |
| Evaluation | Authored 30 questions with gold answers/sections from the policy text, then the scorer | Spot-check gold answers |
| Debugging | Ran tests and the evaluation, found real defects, fixed them (below) | Decide what is acceptable |

## Issues found by running things (not by assumption)
1. mcp SDK 2.x changed its API; pinned `mcp>=1.9,<2` and verified on 1.30.
2. Clarification follow-ups ("3 days starting Monday" after "I need time off") lost context - fixed with resumable state, tested.
3. Out-of-corpus questions (weather, stock options) initially got confident answers from loosely related text. Added an
   IDF-weighted term-coverage guardrail, then an out-of-vocabulary-term rule after the evaluation exposed "stock option vesting"
   matching "401(k) vested". That rule briefly broke "US holidays" (the word "US"); the escalation metric caught it and short tokens are now exempt.
4. A generic multi-topic new-hire question was misrouted to the personal expense workflow - fixed, regression test added.

## Setup, deployment and live testing (also with Claude Code)
Claude Code was used to wire up environment variables, run the app locally, test the live LLM, deploy to Render and harden CI/CD.
What it caught by actually running things:
5. `.env` was never loaded (settings read only real env vars) - added `python-dotenv`; real env vars still take precedence.
6. The GitHub Actions workflow sat inside the project subfolder, where GitHub never runs it - moved to the repo root,
   scoped to this folder.
7. Live LLM calls returned 404 because `LLM_BASE_URL` was set to the full `.../chat/completions` URL and the client appends
   that path again - the client now accepts either form (test added).
8. The post-deploy `/health` smoke test passed instantly against the *old* Render instance while the new one was still building -
   it now only accepts an instance whose uptime is shorter than the time since the deploy hook fired.
9. A `--quick` evaluation run overwrote the full results report - regenerated with the full run.

What worked well: running the real stack (tests, eval, uvicorn, live `/chat` calls) after every change, so problems surfaced
as failures instead of assumptions. What needed a human: choosing the LLM provider, creating the API key and Render service,
and pasting secrets (never shared in chat).

## Honest limitations
- The evaluation set was written by the same AI alongside development, and fixes in item 3-4 were made after seeing eval
  failures, so the final scores are **tuned on the dev set** and optimistic. A held-out set written by someone else would be better.
- The "embeddings" are TF-IDF + LSA (SVD), not a neural model - chosen to run offline on a free tier.
- The agent is a deterministic workflow planner calling MCP tools, not an LLM tool-calling loop.
- The LLM path (GPT-4o via OpenRouter) was smoke-tested live on a handful of prompts, locally and on Render, but not
  evaluated at scale; the reported metrics are from the deterministic no-LLM mode.
- Deployment, the GitHub repo, the demo video and identity verification are done by the submitter, not by AI.
