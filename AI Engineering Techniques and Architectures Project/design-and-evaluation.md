# Design and evaluation

## 1. Architecture

```
Browser chat UI ──HTTP──▶ FastAPI (app/main.py)  /chat /confirm /cancel /health /tools
                              │
                              ▼
                        HRAgent (app/agent.py)
        NLU (rules; optional LLM for low-confidence intents) → workflow planner → answer templates
                              │  every tool call is a typed trace step
                              ▼
                  MCPClient (app/mcp_client.py)  — discovers tools with list_tools
                              │   stdio subprocess (default)  or  streamable-HTTP (MCP_SERVER_URL)
                              ▼
                  MCP server "northwind-hr" (mcp_server/server.py, FastMCP, 8 tools)
             ┌───────────────┴────────────────┐
             ▼                                ▼
   RAG index (rag/): FAISS + TF-IDF     mock_data/*.json  (+ runtime/tickets_created.json)
   over corpus/ (17 docs, md/html/txt)
```

Tools are **only** reachable through the MCP layer: the agent has no direct import of the tool implementations, and
`tests/test_mcp.py` plus the evaluation run the real server over stdio.

## 2. RAG design
- **Corpus:** 17 synthetic policies (POL-001..017), markdown / HTML / plain text, ~12.6k words (~31 pages at 400 words/page).
- **Parsing & chunking:** format-specific parsers produce numbered sections; heading-aware chunks of 180 words with 40 overlap,
  sections kept whole up to 1.25x. Every chunk carries doc id, title, section number/heading, source file.
- **Retrieval:** hybrid score = 0.5 x dense (TF-IDF -> TruncatedSVD/LSA 128-d, L2-normalised, FAISS `IndexFlatIP`) + 0.5 x sparse
  (TF-IDF cosine, stemming analyzer, unigrams+bigrams) + a small heading-match boost; light query rewriting for common synonyms.
- **Evidence guardrail:** an answer needs max score >= 0.22 and IDF-weighted query-term coverage >= 0.6 in the top-3 chunks
  (>= 0.85 when the question contains a word that appears nowhere in the corpus). Otherwise the agent refuses rather than guesses,
  or - if it only partly covers the topic - says so explicitly ("Heads-up: the policies don't directly address ...").
- **Citations:** `[POL-001 §5]`; each is checked to exist, given a snippet from the real section text, and unverifiable ones are removed.

## 3. MCP tools (8)
| Tool | Purpose | Side effects |
|---|---|---|
| `search_policy_documents(query, top_k, doc_id?)` | hybrid retrieval + `evidence` block | none |
| `get_policy_section(doc_id, section)` | exact section text (citation target) | none |
| `lookup_employee_profile(employee_id)` | role, office/country, type, tenure, intro-period status, manager | none |
| `check_pto_balance(employee_id, days_requested?)` | entitlement, carryover, used, pending, available, sufficiency | none |
| `lookup_benefits_status(employee_id)` | eligibility derived from type/hours/country + elections | none |
| `check_policy_compliance(employee_id, scenario, ...)` | rule engine for `pto_request`, `remote_work`, `expense`; returns per-rule checks each citing a section and the approvals required | none |
| `draft_hr_email(employee_id, recipient, purpose, details?)` | drafts an email | **never sends** |
| `create_mock_hr_ticket(..., confirmed=false)` | mock ticket | writes **only** if `confirmed=true` |

## 4. Agent design
Deterministic orchestration (no agent framework): classify intent and extract slots -> plan -> call MCP tools -> reason over
results -> build a grounded answer with citations, drafts, escalation and trace. Workflows: PTO request, PTO balance, remote work,
expense, benefits, HR case, policy Q&A, clarification. Missing information triggers a **clarifying question** whose state is
carried to the next turn. If MCP is unreachable the agent degrades with an explicit message instead of inventing data.

**Example (E1001, "3 days of PTO next week"):** profile -> PTO balance (7.75 available: sufficient) -> policy search ->
compliance check (notice 2 business days vs 10 required: **needs manager exception**) -> email draft -> ticket **preview**
awaiting the user's Confirm button.

**Action safety:** `_call` forces `confirmed=False` on every ticket call from the agent; only `/confirm`, triggered by a human
click, passes `True`; pending actions are single-use with a 30-minute TTL. The evaluation verifies `/chat` never writes tickets.

## 5. Evaluation
`evaluation/questions.json`: 30 items - policy_qa 8, multi_doc 3, tool_task 10, ambiguous 3, out_of_scope 3, escalation 2, safety 1 -
each with gold behavior, intent, required/forbidden tools, gold docs/sections, gold answer, gold keywords, escalation and pending-action expectations.
Run: `python -m evaluation.run_eval`. Outputs: `evaluation/results/{results.json,results.md,per_question.csv}`.

**Metrics** (all computed per question, then averaged): behavior (answer/clarify/refuse/escalate), tool selection (required tools
all called, no forbidden tool called), workflow completion (right behavior + tools + pending-action state + gold keywords),
citation validity (snippet really inside the cited section), citation accuracy (cited section is a gold section),
groundedness (see caveat), escalation/clarification accuracy, action safety (ticket store unchanged by every `/chat`), latency.

### Results (deterministic mode, LLM off, reference date 2026-10-01)
| Metric | Result |
|---|---|
| Behavior accuracy | 30/30 (1.00) |
| Intent accuracy | 29/30 (0.967) - q26 "stock option vesting" is routed `out_of_scope`, my gold said `policy_qa`; the refusal is correct either way |
| Tool selection | 1.00 |
| Workflow completion | 1.00 |
| Citation validity / gold-section accuracy | 1.00 / 1.00 |
| Numeric groundedness | 1.00 |
| Escalation accuracy / clarification / refusal | 1.00 / 1.00 / 1.00 |
| Action safety (no ticket written without confirm) | 1.00 |
| Latency, agent level (in-process, real MCP) p50 / p95 | 18.9 ms / 44.0 ms |
| Latency, HTTP level (TestClient, 15 queries) p50 / p95 | 12.7 ms / 39.0 ms |
| Cold start, local | MCP spawn + discovery 1.2-1.3 s; index build 0.29 s |

**How to read these honestly.** The question set was written by the same author as the system and several fixes were made after
seeing failures, so these numbers are optimistic. The first full run scored behavior 0.933 / refusal 0.667: q26 (stock options)
got a confident but irrelevant answer and q11 (generic new-hire question) was mis-routed. Fixing them (an out-of-vocabulary-term rule in the
guardrail; a generic-subject check in the NLU) first introduced a regression on q02 ("US" treated as unknown), caught by the escalation
metric, then fixed. Regression tests cover both. Latency is tiny because there is no LLM call and the corpus is small;
with an LLM enabled, expect the provider's latency to dominate. "Groundedness" is a **lexical/numeric proxy** (every number in an answer must appear in the
cited text, tool output or question; every citation must resolve), not a human or LLM-judge faithfulness score.

### Ablations
Retrieval ablations score the retriever alone on the 24 answerable questions with gold sections (section hit@k = a gold section is in the top k; MRR).

| Variant | Section hit@k | MRR |
|---|---|---|
| top-k = 1 / 3 / **5** / 8 | 0.50 / 0.79 / **0.79** / 0.79 | 0.50 / 0.62 / 0.62 / 0.62 |
| chunk 80w / 120w / **180w (default)** / 300w / 180w no overlap | 0.83 / 0.79 / **0.79** / 0.79 / 0.79 | 0.65 / 0.61 / 0.62 / 0.62 / 0.62 |
| sparse only / **hybrid** / dense only (LSA) | 0.79 / **0.79** / 0.79 | 0.59 / **0.62** / 0.63 |

Takeaways: k=1 clearly hurts (top-3 recovers +29 points); beyond 3 nothing changes. Chunk size, overlap and retrieval mode differ by
at most one question out of 24, i.e. **no meaningful difference on this small, sections-aligned corpus** - I'm not claiming hybrid beats
dense. Retriever-only section hit (0.79) is below end-to-end citation accuracy (1.00) because the agent issues topic-specific rewrites,
multiple queries for multi-topic questions and calls `get_policy_section`.

Tool-availability ablation (12 tool_task + escalation questions):

| Tools available | Tool selection | Workflow completion | Keyword recall | Behavior |
|---|---|---|---|---|
| full (8) | 1.00 | 1.00 | 1.00 | 1.00 |
| no `check_policy_compliance` | 0.33 | 0.33 | 0.38 | 0.75 |
| no profile/balance/benefits tools | 0.17 | 0.17 | 0.17 | 0.92 |
| RAG only | 0.17 | 0.00 | 0.17 | 0.92 |

Tool selection and workflow completion fall by construction (required tools are defined as those tools); the independent signals are keyword
recall (answers lose the personalised facts such as balance and required notice) and behavior. Takeaway: the structured tools, not retrieval, carry the task workflows.

## 6. Limitations
Embeddings are LSA not neural; the agent is a deterministic planner, not an LLM tool-calling loop; the LLM path was only smoke-tested live
(GPT-4o via OpenRouter, a handful of prompts), not evaluated at scale; the eval set is small, self-authored and dev-tuned; free-tier cold start is not measured here; policies and employees are fictional
and the rule engine encodes only the policies in the corpus (it is not legal or HR advice).
