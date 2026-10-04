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

## Honest limitations
- The evaluation set was written by the same AI alongside development, and fixes in item 3-4 were made after seeing eval
  failures, so the final scores are **tuned on the dev set** and optimistic. A held-out set written by someone else would be better.
- The "embeddings" are TF-IDF + LSA (SVD), not a neural model - chosen to run offline on a free tier.
- The agent is a deterministic workflow planner calling MCP tools, not an LLM tool-calling loop.
- The LLM path was never exercised against a real provider in the build environment.
- Deployment, the GitHub repo, the demo video and identity verification are done by the submitter, not by AI.
