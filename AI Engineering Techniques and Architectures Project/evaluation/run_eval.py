"""Evaluation harness for the Northwind HR agent.

Runs the 30 questions in evaluation/questions.json through the REAL agent + MCP server (stdio subprocess) and scores:

  per question  behavior (answer/clarify/refuse/escalate), intent, tool selection (required subset, forbidden empty),
                workflow completion, citation validity (snippet really is inside the cited section), citation accuracy
                (cited section is a gold section), gold-doc recall (cited or retrieved), gold-keyword match,
                numeric groundedness, escalation accuracy, pending-action expectation, action safety
  latency       agent-level p50/p95, HTTP-level (FastAPI TestClient), cold start (fresh MCP spawn, index build)
  ablations     retrieval top-k, chunk size/overlap, retrieval mode (dense/sparse/hybrid), tool availability

Usage:
  python -m evaluation.run_eval                 # full run, writes evaluation/results/*
  python -m evaluation.run_eval --quick         # CI mode: main run only, exits non-zero below thresholds
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Deterministic environment: fixed "today", isolated ticket store, no LLM (so results do not depend on a provider).
os.environ.setdefault("APP_TODAY", "2026-10-01")
_RUNTIME = tempfile.mkdtemp(prefix="eval_runtime_")
os.environ["RUNTIME_DIR"] = _RUNTIME
os.environ["LLM_API_KEY"] = ""

import settings  # noqa: E402
from app.agent import CITE_RE, HRAgent  # noqa: E402
from app.llm import LLM  # noqa: E402
from app.mcp_client import MCPClient  # noqa: E402
from rag import index as rag_index  # noqa: E402
from rag.index import PolicyIndex  # noqa: E402

RESULTS = ROOT / "evaluation" / "results"
QUESTIONS = ROOT / "evaluation" / "questions.json"
TICKETS = Path(_RUNTIME) / "tickets_created.json"

# CI gate thresholds (quick mode)
THRESHOLDS = {"behavior_accuracy": 0.90, "tool_selection": 0.90, "citation_validity": 0.95, "action_safety": 1.0, "numeric_groundedness": 0.95}

NUM_RE = re.compile(r"(?<![\w§#-])(\d+(?:[.,]\d+)*)(?![\w-])")


# --------------------------------------------------------------------------- helpers
def pct(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    k = (len(s) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 1)


def norm_ws(t: str) -> str:
    return re.sub(r"[\s*_`>|]+", " ", t).strip().lower()


def norm_num(s: str) -> str:
    s = s.replace(",", "")
    try:
        f = float(s)
        return str(int(f)) if f == int(f) else str(f)
    except ValueError:
        return s


def numbers_in(text: str) -> set[str]:
    return {norm_num(m) for m in NUM_RE.findall(text)}


def tickets_snapshot() -> str:
    return TICKETS.read_text() if TICKETS.exists() else ""


def observed_behavior(r: dict) -> str:
    if r["needs_clarification"]:
        return "clarify"
    refused = any(s["type"] == "guardrail" and "insufficient evidence" in s["title"].lower() for s in r["trace"])
    if refused and not r["citations"]:
        return "refuse"
    if r["escalation"]["needed"] and r["intent"] == "hr_case":
        return "escalate"
    return "answer"


def retrieved_sections(r: dict) -> set[str]:
    out = set()
    for s in r["trace"]:
        if s["type"] == "tool_call" and s.get("tool") == "search_policy_documents" and isinstance(s.get("output"), dict):
            for x in s["output"].get("results", []):
                m = re.search(r"(\d+)", x.get("section", "").replace(x["doc_id"], ""))
                if m:
                    out.add(f"{x['doc_id']}#{m.group(1)}")
    return out


# --------------------------------------------------------------------------- main run
async def score_question(agent: HRAgent, idx: PolicyIndex, q: dict) -> dict:
    exp = q["expected"]
    before = tickets_snapshot()
    t0 = time.perf_counter()
    r = await agent.handle(q["query"], q.get("employee_id"))
    wall_ms = round((time.perf_counter() - t0) * 1000, 1)
    after = tickets_snapshot()
    called = set(r["tools_called"])
    obs = observed_behavior(r)
    cites = [f"{c['doc_id']}#{c['section_number']}" for c in r["citations"]]
    gold_secs = set(exp.get("gold_sections", []))
    gold_docs = set(exp.get("gold_docs", []))
    retrieved = retrieved_sections(r)
    answer = r["answer"]

    # citation validity: every cited snippet must be (a normalised) substring of the cited section's real text
    valid = []
    for c in r["citations"]:
        sec = idx.get_section(c["doc_id"], c["section_number"])
        valid.append(bool(sec) and norm_ws(c["snippet"]).rstrip(". …") in norm_ws(sec["text"]))
    # every [POL-xxx §n] tag in the answer must resolve to a returned citation
    tags = {f"{a}#{b}" for a, b in CITE_RE.findall(answer)}
    tag_ok = tags <= set(cites)

    # numeric groundedness
    allowed_text = [q["query"], settings.today().isoformat()]
    for c in r["citations"]:
        sec = idx.get_section(c["doc_id"], c["section_number"])
        allowed_text.append(sec["text"] if sec else "")
    for s in r["trace"]:
        if s["type"] == "tool_call":
            allowed_text.append(json.dumps(s.get("arguments", {})) + json.dumps(s.get("output", {})))
    for e in r["evidence"]:
        allowed_text.append(json.dumps(e))
    # full text of every retrieved chunk is also admissible evidence
    for d_s in retrieved:
        d, s_ = d_s.split("#")
        sec = idx.get_section(d, s_)
        allowed_text.append(sec["text"] if sec else "")
    allowed = numbers_in(" ".join(allowed_text))
    ans_nums = numbers_in(CITE_RE.sub("", answer))
    ungrounded = sorted(n for n in ans_nums if n not in allowed)
    num_grounded = 1.0 if not ans_nums else round(1 - len(ungrounded) / len(ans_nums), 3)

    kw = [k for k in exp.get("gold_keywords", [])]
    kw_hit = [k for k in kw if k.lower() in answer.lower()]

    res = {
        "id": q["id"], "category": q["category"], "query": q["query"], "employee_id": q.get("employee_id"),
        "expected_behavior": exp["behavior"], "observed_behavior": obs, "behavior_ok": obs == exp["behavior"],
        "intent_expected": exp.get("intent"), "intent_observed": r["intent"],
        "intent_ok": exp.get("intent") is None or exp["intent"] == r["intent"],
        "tools_called": r["tools_called"],
        "required_ok": set(exp["required_tools"]) <= called, "forbidden_ok": not (set(exp["forbidden_tools"]) & called),
        "missing_tools": sorted(set(exp["required_tools"]) - called), "forbidden_called": sorted(set(exp["forbidden_tools"]) & called),
        "citations": cites, "citation_valid": all(valid) if valid else None, "citation_tags_resolve": tag_ok,
        "citation_gold_hit": (bool(gold_secs & set(cites)) if (gold_secs and exp["behavior"] in ("answer", "escalate")) else None),
        "gold_doc_recall": (round(len(gold_docs & ({c.split('#')[0] for c in cites} | {s.split('#')[0] for s in retrieved})) / len(gold_docs), 3) if gold_docs else None),
        "gold_section_in_retrieved": (bool(gold_secs & retrieved) if gold_secs else None),
        "keyword_recall": round(len(kw_hit) / len(kw), 3) if kw else None, "keywords_missing": [k for k in kw if k not in kw_hit],
        "numeric_groundedness": num_grounded, "ungrounded_numbers": ungrounded,
        "escalation_expected": exp.get("escalation_needed"), "escalation_observed": r["escalation"]["needed"],
        "escalation_ok": None if exp.get("escalation_needed") is None else bool(exp["escalation_needed"]) == bool(r["escalation"]["needed"]),
        "pending_expected": exp.get("pending_action"), "pending_observed": bool(r["pending_actions"]),
        "pending_ok": bool(exp.get("pending_action")) == bool(r["pending_actions"]),
        "action_safe": before == after,  # nothing may be written to the ticket store by /chat
        "latency_ms": r["latency_ms"], "wall_ms": wall_ms, "answer": answer,
    }
    # workflow completion: the right outcome + all required tools + no forbidden tools + expected pending action state
    res["workflow_complete"] = bool(res["behavior_ok"] and res["required_ok"] and res["forbidden_ok"] and res["pending_ok"]
                                    and (res["keyword_recall"] in (None, 1.0) or exp["behavior"] in ("clarify", "refuse")))
    return res


def mean(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


def aggregate(rows: list[dict]) -> dict:
    b = lambda k: mean([1.0 if r[k] else 0.0 for r in rows if r[k] is not None])  # noqa: E731
    tool_rows = [r for r in rows if r["expected_behavior"] in ("answer", "escalate") or r["category"] == "safety"]
    lat = [r["latency_ms"] for r in rows]
    return {
        "n": len(rows),
        "behavior_accuracy": b("behavior_ok"), "intent_accuracy": b("intent_ok"),
        "tool_selection": mean([1.0 if (r["required_ok"] and r["forbidden_ok"]) else 0.0 for r in rows]),
        "workflow_completion": b("workflow_complete"),
        "citation_validity": b("citation_valid"), "citation_tags_resolve": b("citation_tags_resolve"),
        "citation_accuracy_gold": b("citation_gold_hit"),
        "gold_doc_recall": mean([r["gold_doc_recall"] for r in rows]),
        "gold_section_retrieved": b("gold_section_in_retrieved"),
        "keyword_recall": mean([r["keyword_recall"] for r in tool_rows]),
        "numeric_groundedness": mean([r["numeric_groundedness"] for r in rows]),
        "groundedness_answers_fully_grounded": b_all(rows),
        "escalation_accuracy": b("escalation_ok"), "pending_action_accuracy": b("pending_ok"),
        "action_safety": b("action_safe"),
        "clarification_accuracy": mean([1.0 if r["behavior_ok"] else 0.0 for r in rows if r["expected_behavior"] == "clarify"]),
        "refusal_accuracy": mean([1.0 if r["behavior_ok"] else 0.0 for r in rows if r["expected_behavior"] == "refuse"]),
        "latency_ms": {"p50": pct(lat, 50), "p95": pct(lat, 95), "mean": round(statistics.mean(lat), 1), "max": max(lat)},
    }


def b_all(rows):
    return mean([1.0 if not r["ungrounded_numbers"] else 0.0 for r in rows])


def by_category(rows):
    out = {}
    for cat in sorted({r["category"] for r in rows}):
        sub = [r for r in rows if r["category"] == cat]
        out[cat] = {"n": len(sub), "behavior_accuracy": mean([1.0 if r["behavior_ok"] else 0.0 for r in sub]),
                    "tool_selection": mean([1.0 if (r["required_ok"] and r["forbidden_ok"]) else 0.0 for r in sub]),
                    "workflow_completion": mean([1.0 if r["workflow_complete"] else 0.0 for r in sub])}
    return out


async def run_main(questions: list[dict], allowed_tools: set[str] | None = None) -> tuple[list[dict], dict]:
    mcp = MCPClient()
    t0 = time.perf_counter()
    await mcp.start()
    startup_ms = round((time.perf_counter() - t0) * 1000)
    try:
        agent = HRAgent(mcp, LLM(), allowed_tools=allowed_tools)
        idx = PolicyIndex.load_or_build()
        rows = [await score_question(agent, idx, q) for q in questions]
    finally:
        await mcp.close()
    return rows, {"mcp_startup_ms": startup_ms}


# --------------------------------------------------------------------------- latency
async def cold_start(n: int = 3) -> dict:
    spawn, first = [], []
    for _ in range(n):
        m = MCPClient()
        t0 = time.perf_counter()
        await m.start()
        spawn.append((time.perf_counter() - t0) * 1000)
        r = await m.call_tool("search_policy_documents", {"query": "PTO carryover", "top_k": 3})
        first.append(r["latency_ms"])
        await m.close()
    t0 = time.perf_counter()
    PolicyIndex.from_corpus()
    build_ms = (time.perf_counter() - t0) * 1000
    return {"mcp_spawn_and_discovery_ms": [round(x) for x in spawn], "first_search_ms": [round(x, 1) for x in first],
            "index_build_ms": round(build_ms), "note": "Local numbers. Render free-tier adds container wake-up (~30-60 s after idle) that cannot be measured here."}


def http_latency(questions: list[dict], n: int = 15) -> dict:
    from fastapi.testclient import TestClient
    from app.main import create_app
    sample = [q for q in questions if q["expected"]["behavior"] != "clarify"][:n]
    lat = []
    with TestClient(create_app()) as c:
        c.get("/health")
        for q in sample:
            t0 = time.perf_counter()
            resp = c.post("/chat", json={"message": q["query"], "employee_id": q.get("employee_id")})
            assert resp.status_code == 200
            lat.append((time.perf_counter() - t0) * 1000)
        h0 = time.perf_counter()
        c.get("/health")
        health_ms = (time.perf_counter() - h0) * 1000
    return {"n": len(lat), "p50_ms": pct(lat, 50), "p95_ms": pct(lat, 95), "max_ms": round(max(lat), 1), "health_ms": round(health_ms, 1)}


# --------------------------------------------------------------------------- ablations
def retrieval_eval(index: PolicyIndex, questions: list[dict], k: int) -> dict:
    """Retrieval-only ablation: does the top-k contain a gold section / gold doc? (answerable questions that have gold sections)"""
    qs = [q for q in questions if q["expected"]["gold_sections"] and q["expected"]["behavior"] in ("answer", "escalate")]
    sec_hit = doc_hit = 0
    rr = []
    for q in qs:
        res = index.search(q["query"], top_k=k)["results"]
        gold = set(q["expected"]["gold_sections"])
        gdocs = set(q["expected"]["gold_docs"])
        got = [f"{r['doc_id']}#{r['section_number']}" for r in res]
        sec_hit += bool(gold & set(got))
        doc_hit += bool(gdocs & {r["doc_id"] for r in res})
        rank = next((i for i, g in enumerate(got, 1) if g in gold), None)
        rr.append(1 / rank if rank else 0.0)
    n = len(qs)
    return {"n": n, "section_hit@k": round(sec_hit / n, 3), "doc_hit@k": round(doc_hit / n, 3), "mrr": round(sum(rr) / n, 3), "k": k}


def ablation_retrieval(questions: list[dict]) -> dict:
    out = {}
    base = PolicyIndex.from_corpus()
    out["top_k"] = {str(k): retrieval_eval(base, questions, k) for k in (1, 3, 5, 8)}
    out["chunking"] = {}
    for label, w, o in (("80w/20ov", 80, 20), ("120w/30ov", 120, 30), ("180w/40ov (default)", 180, 40), ("300w/60ov", 300, 60), ("180w/no-overlap", 180, 0)):
        ix = PolicyIndex.from_corpus(w, o)
        out["chunking"][label] = {**retrieval_eval(ix, questions, 5), "chunks": len(ix.chunks)}
    out["mode"] = {}
    old = rag_index.DENSE_WEIGHT
    try:
        for label, wgt in (("sparse only (TF-IDF)", 0.0), ("hybrid 0.5/0.5 (default)", 0.5), ("dense only (LSA+FAISS)", 1.0)):
            rag_index.DENSE_WEIGHT = wgt
            out["mode"][label] = retrieval_eval(base, questions, 5)
    finally:
        rag_index.DENSE_WEIGHT = old
    return out


async def ablation_tools(questions: list[dict]) -> dict:
    qs = [q for q in questions if q["category"] in ("tool_task", "escalation")]
    all_tools = {"search_policy_documents", "get_policy_section", "lookup_employee_profile", "check_pto_balance", "lookup_benefits_status",
                 "create_mock_hr_ticket", "draft_hr_email", "check_policy_compliance"}
    variants = {
        "full (8 tools)": None,
        "no check_policy_compliance": all_tools - {"check_policy_compliance"},
        "no structured-data tools (profile/balance/benefits)": all_tools - {"lookup_employee_profile", "check_pto_balance", "lookup_benefits_status"},
        "RAG only (search + get_section)": {"search_policy_documents", "get_policy_section"},
    }
    out = {}
    for label, allowed in variants.items():
        rows, _ = await run_main(qs, allowed)
        out[label] = {"n": len(rows), "tool_selection": mean([1.0 if (r["required_ok"] and r["forbidden_ok"]) else 0.0 for r in rows]),
                      "workflow_completion": mean([1.0 if r["workflow_complete"] else 0.0 for r in rows]),
                      "keyword_recall": mean([r["keyword_recall"] for r in rows]),
                      "behavior_accuracy": mean([1.0 if r["behavior_ok"] else 0.0 for r in rows])}
    return out


# --------------------------------------------------------------------------- reporting
def write_outputs(rows, agg, extra):
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "results.json").write_text(json.dumps({"summary": agg, "by_category": by_category(rows), **extra, "per_question": rows}, indent=2, default=str))
    cols = ["id", "category", "expected_behavior", "observed_behavior", "behavior_ok", "intent_expected", "intent_observed", "required_ok", "forbidden_ok",
            "missing_tools", "forbidden_called", "citations", "citation_valid", "citation_gold_hit", "keyword_recall", "keywords_missing",
            "numeric_groundedness", "ungrounded_numbers", "escalation_ok", "pending_ok", "action_safe", "workflow_complete", "latency_ms", "query"]
    with open(RESULTS / "per_question.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(r[k]) if isinstance(r[k], (list, dict)) else r[k]) for k in cols})

    L = ["# Evaluation results", "", f"_Reference date {settings.today()}; {agg['n']} questions; deterministic (no-LLM) mode; real MCP server over stdio._", "",
         "## Summary", "", "| Metric | Value |", "|---|---|"]
    for k, v in agg.items():
        if k == "latency_ms":
            L.append(f"| latency p50 / p95 / max (agent-level, ms) | {v['p50']} / {v['p95']} / {v['max']} |")
        elif k != "n":
            L.append(f"| {k} | {v} |")
    L += ["", "## By category", "", "| Category | n | behavior | tool selection | workflow completion |", "|---|---|---|---|---|"]
    for c, v in by_category(rows).items():
        L.append(f"| {c} | {v['n']} | {v['behavior_accuracy']} | {v['tool_selection']} | {v['workflow_completion']} |")
    fails = [r for r in rows if not r["workflow_complete"] or r["citation_valid"] is False or r["ungrounded_numbers"] or not r["action_safe"]]
    L += ["", f"## Questions with any issue ({len(fails)})", ""]
    for r in fails:
        why = []
        if not r["behavior_ok"]:
            why.append(f"behavior {r['observed_behavior']} != {r['expected_behavior']}")
        if r["missing_tools"]:
            why.append(f"missing tools {r['missing_tools']}")
        if r["forbidden_called"]:
            why.append(f"forbidden tools {r['forbidden_called']}")
        if not r["pending_ok"]:
            why.append(f"pending_action expected={r['pending_expected']} observed={r['pending_observed']}")
        if r["keywords_missing"]:
            why.append(f"keywords missing {r['keywords_missing']}")
        if r["citation_valid"] is False:
            why.append("invalid citation snippet")
        if r["ungrounded_numbers"]:
            why.append(f"ungrounded numbers {r['ungrounded_numbers']}")
        if not r["action_safe"]:
            why.append("TICKET WRITTEN WITHOUT CONFIRMATION")
        L.append(f"- **{r['id']}** ({r['category']}): {r['query']} -> " + "; ".join(why))
    for title, key in (("Latency", "latency"), ("Ablation: retrieval", "ablation_retrieval"), ("Ablation: tool availability", "ablation_tools")):
        if key in extra:
            L += ["", f"## {title}", "", "```json", json.dumps(extra[key], indent=2), "```"]
    (RESULTS / "results.md").write_text("\n".join(L) + "\n")


async def amain(args) -> int:
    qs = json.loads(QUESTIONS.read_text())["questions"]
    TICKETS.unlink(missing_ok=True)
    rows, meta = await run_main(qs)
    agg = aggregate(rows)
    extra: dict = {"meta": meta}
    if not args.quick:
        extra["latency"] = {"agent_level": agg["latency_ms"], "http_level": http_latency(qs), "cold_start": await cold_start()}
        extra["ablation_retrieval"] = ablation_retrieval(qs)
        extra["ablation_tools"] = await ablation_tools(qs)
    write_outputs(rows, agg, extra)
    print(json.dumps({k: v for k, v in agg.items()}, indent=2))
    bad = {k: agg[k] for k, t in THRESHOLDS.items() if (agg[k] or 0) < t}
    if bad:
        print("BELOW THRESHOLD:", bad)
    return 1 if (bad and args.quick) else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="CI mode: main run only; non-zero exit below thresholds")
    sys.exit(asyncio.run(amain(ap.parse_args())))
