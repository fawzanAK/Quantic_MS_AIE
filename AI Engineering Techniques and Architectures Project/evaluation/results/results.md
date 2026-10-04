# Evaluation results

_Reference date 2026-10-01; 30 questions; deterministic (no-LLM) mode; real MCP server over stdio._

## Summary

| Metric | Value |
|---|---|
| behavior_accuracy | 1.0 |
| intent_accuracy | 0.967 |
| tool_selection | 1.0 |
| workflow_completion | 1.0 |
| citation_validity | 1.0 |
| citation_tags_resolve | 1.0 |
| citation_accuracy_gold | 1.0 |
| gold_doc_recall | 1.0 |
| gold_section_retrieved | 1.0 |
| keyword_recall | 1.0 |
| numeric_groundedness | 1.0 |
| groundedness_answers_fully_grounded | 1.0 |
| escalation_accuracy | 1.0 |
| pending_action_accuracy | 1.0 |
| action_safety | 1.0 |
| clarification_accuracy | 1.0 |
| refusal_accuracy | 1.0 |
| latency p50 / p95 / max (agent-level, ms) | 31.6 / 75.1 / 92.6 |

## By category

| Category | n | behavior | tool selection | workflow completion |
|---|---|---|---|---|
| ambiguous | 3 | 1.0 | 1.0 | 1.0 |
| escalation | 2 | 1.0 | 1.0 | 1.0 |
| multi_doc | 3 | 1.0 | 1.0 | 1.0 |
| out_of_scope | 3 | 1.0 | 1.0 | 1.0 |
| policy_qa | 8 | 1.0 | 1.0 | 1.0 |
| safety | 1 | 1.0 | 1.0 | 1.0 |
| tool_task | 10 | 1.0 | 1.0 | 1.0 |

## Questions with any issue (0)


## Latency

```json
{
  "agent_level": {
    "p50": 31.6,
    "p95": 75.1,
    "mean": 35.7,
    "max": 92.6
  },
  "http_level": {
    "n": 15,
    "p50_ms": 21.0,
    "p95_ms": 75.4,
    "max_ms": 92.3,
    "health_ms": 18.2
  },
  "cold_start": {
    "mcp_spawn_and_discovery_ms": [
      3304,
      3228,
      3397
    ],
    "first_search_ms": [
      35.9,
      30.5,
      27.5
    ],
    "index_build_ms": 701,
    "note": "Local numbers. Render free-tier adds container wake-up (~30-60 s after idle) that cannot be measured here."
  }
}
```

## Ablation: retrieval

```json
{
  "top_k": {
    "1": {
      "n": 24,
      "section_hit@k": 0.5,
      "doc_hit@k": 0.75,
      "mrr": 0.5,
      "k": 1
    },
    "3": {
      "n": 24,
      "section_hit@k": 0.792,
      "doc_hit@k": 0.917,
      "mrr": 0.618,
      "k": 3
    },
    "5": {
      "n": 24,
      "section_hit@k": 0.792,
      "doc_hit@k": 0.917,
      "mrr": 0.618,
      "k": 5
    },
    "8": {
      "n": 24,
      "section_hit@k": 0.792,
      "doc_hit@k": 0.917,
      "mrr": 0.618,
      "k": 8
    }
  },
  "chunking": {
    "80w/20ov": {
      "n": 24,
      "section_hit@k": 0.833,
      "doc_hit@k": 0.917,
      "mrr": 0.651,
      "k": 5,
      "chunks": 217
    },
    "120w/30ov": {
      "n": 24,
      "section_hit@k": 0.792,
      "doc_hit@k": 0.917,
      "mrr": 0.608,
      "k": 5,
      "chunks": 183
    },
    "180w/40ov (default)": {
      "n": 24,
      "section_hit@k": 0.792,
      "doc_hit@k": 0.917,
      "mrr": 0.618,
      "k": 5,
      "chunks": 180
    },
    "300w/60ov": {
      "n": 24,
      "section_hit@k": 0.792,
      "doc_hit@k": 0.917,
      "mrr": 0.618,
      "k": 5,
      "chunks": 179
    },
    "180w/no-overlap": {
      "n": 24,
      "section_hit@k": 0.792,
      "doc_hit@k": 0.917,
      "mrr": 0.618,
      "k": 5,
      "chunks": 180
    }
  },
  "mode": {
    "sparse only (TF-IDF)": {
      "n": 24,
      "section_hit@k": 0.792,
      "doc_hit@k": 0.917,
      "mrr": 0.59,
      "k": 5
    },
    "hybrid 0.5/0.5 (default)": {
      "n": 24,
      "section_hit@k": 0.792,
      "doc_hit@k": 0.917,
      "mrr": 0.618,
      "k": 5
    },
    "dense only (LSA+FAISS)": {
      "n": 24,
      "section_hit@k": 0.792,
      "doc_hit@k": 0.917,
      "mrr": 0.625,
      "k": 5
    }
  }
}
```

## Ablation: tool availability

```json
{
  "full (8 tools)": {
    "n": 12,
    "tool_selection": 1.0,
    "workflow_completion": 1.0,
    "keyword_recall": 1.0,
    "behavior_accuracy": 1.0
  },
  "no check_policy_compliance": {
    "n": 12,
    "tool_selection": 0.333,
    "workflow_completion": 0.333,
    "keyword_recall": 0.375,
    "behavior_accuracy": 0.75
  },
  "no structured-data tools (profile/balance/benefits)": {
    "n": 12,
    "tool_selection": 0.167,
    "workflow_completion": 0.167,
    "keyword_recall": 0.167,
    "behavior_accuracy": 0.917
  },
  "RAG only (search + get_section)": {
    "n": 12,
    "tool_selection": 0.167,
    "workflow_completion": 0.0,
    "keyword_recall": 0.167,
    "behavior_accuracy": 0.917
  }
}
```
