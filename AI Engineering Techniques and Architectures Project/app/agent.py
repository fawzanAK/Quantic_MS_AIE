"""Agent orchestrator (manual orchestration, no framework).

Pipeline per request
  1. understand  : slot extraction + intent classification (LLM only as a low-confidence fallback)
  2. plan        : choose a workflow (which MCP tools, in which order) and log it
  3. act         : call tools through the MCP client (discovery -> call), logging args / outputs / latency
  4. guard       : evidence sufficiency, missing-ID / ambiguity clarification, MCP-down degradation, escalation
  5. synthesise  : grounded answer (LLM if configured, deterministic template otherwise) + citation/number validation
  6. safety      : mutating actions are PREVIEWED via MCP and only executed by /confirm (explicit user confirmation)
The trace records operational steps only (no hidden chain-of-thought).
"""
from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

import settings
from app import nlu
from app.llm import LLM, LLMError
from app.mcp_client import MCPClient
from rag.text import tokens

CITE_RE = re.compile(r"\[(POL-\d{3})\s*§\s*(\d+)\]")
HR_CONTACT = "the People team (people@northwind.example)"
STATUS_LABEL = {"pass": "✔ Pass", "fail": "✖ Not met", "needs_approval": "⚠ Needs approval", "info": "ℹ Note"}
RULE_LABEL = {"introductory_period": "Introductory period", "notice_period": "Notice period", "balance": "PTO balance", "eligibility": "Eligibility",
              "finance_quarter_end_blackout": "Quarter-end blackout", "duration_limit": "Duration limit", "sanctioned_destination": "Destination restrictions",
              "approved_country": "Approved country (data access)", "security_review": "Security review", "data_access": "Data access",
              "tax_notification": "Payroll tax", "destination": "Destination", "equipment_not_reimbursable": "Equipment",
              "home_office_eligibility": "Home office stipend", "stipend_limit": "Stipend limit", "lodging_cap": "Lodging cap", "meal_per_diem": "Meal per diem",
              "airfare_class": "Airfare class", "client_entertainment": "Client entertainment", "receipt": "Receipt", "general": "General rules",
              "request_details": "Request details"}


def _tag(doc: str, sec: str) -> str:
    return f"[{doc} §{sec}]"


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9$\-])|\n+", text)
    return [p.strip(" -•\t") for p in parts if len(p.strip(" -•\t")) > 20]


def pick_sentences(query: str, text: str, n: int = 2) -> list[str]:
    qt = set(tokens(query))
    quantity = bool(re.search(r"how (?:many|much|long)|limit|maximum|max\b|minimum|when|deadline|cap\b|up to|amount|notice|match", query, re.I))
    sents = _split_sentences(re.sub(r"\s-\s(?=[A-Z])", "\n", text))  # inline bullets -> separate sentences
    scored = [(len(qt & set(tokens(s))) + ((1.0 if quantity else 0.5) if re.search(r"\d", s) else 0.0), i, s) for i, s in enumerate(sents)]
    top = sorted(scored, key=lambda x: (-x[0], x[1]))[:n]
    return [s for _, _, s in sorted(top, key=lambda x: x[1])]


class Run:
    """Per-request scratchpad."""

    def __init__(self, message: str):
        self.message = message
        self.t0 = time.perf_counter()
        self.trace: list[dict] = []
        self.evidence: dict[str, dict] = {}  # chunk_id -> chunk (best score)
        self.query_evidence: list[dict] = []
        self.rewritten: list[str] = []
        self.results: dict[str, Any] = {}
        self.tools_called: list[str] = []
        self.pending: list[dict] = []
        self.drafts: list[dict] = []
        self.answer = ""
        self.needs_clarification = False
        self.state: dict | None = None
        self.escalation: dict = {"needed": False, "reason": None, "route": None}
        self.degraded = False
        self.llm_used = {"intent": False, "synthesis": False}
        self.intent = "unknown"
        self.facts_for_llm: dict[str, Any] = {}

    def step(self, type_: str, title: str, **kw) -> dict:
        item = {"step": len(self.trace) + 1, "type": type_, "title": title, "t_ms": round((time.perf_counter() - self.t0) * 1000, 1), **kw}
        self.trace.append(item)
        return item


class HRAgent:
    def __init__(self, mcp: MCPClient, llm: LLM | None = None, allowed_tools: set[str] | None = None):
        self.mcp = mcp
        self.llm = llm or LLM()
        self.allowed_tools = allowed_tools  # used by the tool-availability ablation
        self._pending: dict[str, dict] = {}

    # ================================================================== public API
    async def handle(self, message: str, employee_id: str | None = None, state: dict | None = None) -> dict:
        run = Run(message.strip())
        today = settings.today()
        state = state or {}
        slots = nlu.extract_slots(run.message, today)
        prev_intent = state.get("intent") if state.get("awaiting") else None
        merged = {**state.get("slots", {}), **slots} if prev_intent else dict(slots)
        if employee_id:
            merged["employee_id"] = employee_id.strip().upper()
        cls = nlu.classify(run.message, merged if prev_intent else slots)
        intent = cls["intent"]
        if prev_intent and (intent in ("ambiguous", "out_of_scope") or (intent == "policy_qa" and not cls["topics"])):
            intent = prev_intent
            cls["reasons"].append(f"continuing clarification for '{prev_intent}'")
        if self.llm.configured and cls["confidence"] < 0.7 and intent in ("ambiguous", "out_of_scope"):
            intent = await self._llm_intent(run, intent)
        run.intent = intent
        run.step("intent", "Interpreted request", status="ok", summary=f"intent={intent} (confidence {cls['confidence']:.2f})",
                 output={"intent": intent, "reasons": cls["reasons"], "topics": cls["topics"],
                         "slots": {k: v for k, v in merged.items() if k not in ("duration_text", "date_text")}})

        handler = {"pto_request": self._pto_request, "pto_balance": self._pto_balance, "remote_work": self._remote_work, "expense": self._expense,
                   "benefits": self._benefits, "hr_case": self._hr_case, "policy_qa": self._policy_qa, "out_of_scope": self._policy_qa,
                   "ambiguous": self._ambiguous}[intent]
        try:
            await handler(run, merged, cls)
        except Exception as e:  # noqa: BLE001 - last-resort guard: never crash the chat
            run.step("error", "Unexpected error while handling request", status="error", summary=f"{type(e).__name__}: {e}")
            run.answer = f"Sorry - something went wrong while processing that request. Please try again or contact {HR_CONTACT}."
            run.escalation = {"needed": True, "reason": "internal error", "route": "People team"}
        citations = await self._finalize_citations(run)
        return self._response(run, citations)

    async def confirm(self, action_id: str) -> dict:
        act = self._pending.pop(action_id, None)
        if not act:
            return {"ok": False, "error": "Unknown or expired action_id (already confirmed, cancelled or timed out)."}
        if act["tool"] != "create_mock_hr_ticket":
            return {"ok": False, "error": "Only mock HR ticket creation can be confirmed."}
        res = await self.mcp.call_tool("create_mock_hr_ticket", {**act["arguments"], "confirmed": True})
        return {"ok": res["ok"], "tool": act["tool"], "arguments": {**act["arguments"], "confirmed": True}, "result": res["data"], "error": res["error"],
                "latency_ms": res["latency_ms"]}

    def cancel(self, action_id: str) -> dict:
        return {"ok": self._pending.pop(action_id, None) is not None}

    # ================================================================== infrastructure
    async def _call(self, run: Run, tool: str, args: dict, why: str) -> dict:
        args = {k: v for k, v in args.items() if v is not None}
        if tool == "create_mock_hr_ticket":
            args["confirmed"] = False  # hard rule: only /confirm may pass confirmed=True
        if (self.allowed_tools is not None and tool not in self.allowed_tools) or (self.mcp.tools and tool not in self.mcp.tool_names):
            run.step("tool_call", f"{tool} (unavailable)", tool=tool, arguments=args, status="skipped", why=why, summary="tool not available to the agent")
            return {"ok": False, "data": None, "error": f"tool {tool} unavailable", "unavailable": True, "latency_ms": 0}
        res = await self.mcp.call_tool(tool, args)
        run.tools_called.append(tool)
        if res.get("unavailable"):
            run.degraded = True
        data = res["data"]
        if res["ok"]:
            run.results[tool] = data
        run.step("tool_call", f"MCP tool: {tool}", tool=tool, arguments=args, status="ok" if res["ok"] else "error", latency_ms=res["latency_ms"], why=why,
                 summary=self._summarize(tool, data) if res["ok"] else f"error: {res['error']}", output=self._trim(tool, data))
        return res

    @staticmethod
    def _trim(tool: str, data: Any) -> Any:
        if tool == "search_policy_documents" and isinstance(data, dict):
            return {"rewritten_query": data.get("rewritten_query"), "evidence": data.get("evidence"),
                    "results": [{k: r[k] for k in ("rank", "doc_id", "section", "score", "snippet")} for r in data.get("results", [])]}
        if tool == "get_policy_section" and isinstance(data, dict):
            return {**{k: v for k, v in data.items() if k != "text"}, "text": (data.get("text", "")[:240] + "…")}
        return data

    @staticmethod
    def _summarize(tool: str, d: Any) -> str:
        if not isinstance(d, dict):
            return str(d)[:120]
        if tool == "search_policy_documents":
            r = d.get("results", [])
            top = f"{r[0]['doc_id']} {r[0]['section']} ({r[0]['score']})" if r else "none"
            return f"{len(r)} chunks; top: {top}; evidence sufficient={d['evidence']['sufficient']} (coverage {d['evidence']['term_coverage']})"
        if tool == "get_policy_section":
            return f"{d['doc_id']} {d['section']} ({len(d['text'].split())} words)"
        if tool == "lookup_employee_profile":
            return f"{d['name']}, {d['role']} ({d['department']}, {d['office']}); {d['employment_type']}; tenure {d['tenure_years']}y; intro period={d['in_intro_period']}"
        if tool == "check_pto_balance":
            if not d.get("pto_eligible"):
                return "not PTO-eligible"
            extra = f"; request {d['days_requested']:g}d -> {'sufficient' if d['sufficient_balance'] else 'INSUFFICIENT'}" if "days_requested" in d else ""
            return f"available {d['available_days']:g}d (annual entitlement {d['annual_entitlement_days']:g}d){extra}"
        if tool == "lookup_benefits_status":
            return f"{d['employment_type']}: {d['eligibility']['summary'][:90]}"
        if tool == "check_policy_compliance":
            return f"overall={d['overall']}; " + ", ".join(f"{c['rule']}={c['status']}" for c in d["checks"])
        if tool == "create_mock_hr_ticket":
            return f"status={d['status']} (created={d['created']})"
        if tool == "draft_hr_email":
            return f"draft to {d['to']['name']} (sent={d['sent']})"
        return json.dumps(d)[:120]

    async def _retrieve(self, run: Run, queries: list[str], top_k: int | None = None, doc_id: str | None = None) -> dict | None:
        """Run one search per query through MCP; merge evidence. Returns the evidence block of the first (primary) query."""
        primary = None
        for i, q in enumerate(queries):
            res = await self._call(run, "search_policy_documents", {"query": q, "top_k": top_k or settings.TOP_K, "doc_id": doc_id},
                                   "retrieve policy evidence" + ("" if i == 0 else f" (sub-query {i + 1} for multi-document coverage)"))
            if not res["ok"]:
                continue
            d = res["data"]
            run.rewritten.append(d.get("rewritten_query", q))
            if primary is None:
                primary = d["evidence"]
            run.query_evidence.append({"query": q, **d["evidence"]})
            for r in d["results"]:
                old = run.evidence.get(r["chunk_id"])
                if old is None or r["score"] > old["score"]:
                    run.evidence[r["chunk_id"]] = r
        return primary

    def _ranked_evidence(self, run: Run, min_rel: float = 0.5) -> list[dict]:
        ev = [c for c in run.evidence.values() if c["section_number"] != "0"]
        ev.sort(key=lambda c: -c["score"])
        if not ev:
            return []
        return [c for c in ev if c["score"] >= ev[0]["score"] * min_rel]

    # ------------------------------------------------------------------ common sub-flows
    def _clarify(self, run: Run, question: str, slots: dict, why: str, resume: str | None = None) -> None:
        """Ask the user for missing information. `resume` is the workflow to continue when they answer."""
        run.answer, run.needs_clarification = question, True
        target = resume or (None if run.intent == "ambiguous" else run.intent)
        run.state = {"intent": target, "slots": dict(slots), "awaiting": True} if target else None
        run.step("decision", "Ask for clarification instead of guessing", status="ok", summary=why)

    def _degrade(self, run: Run) -> None:
        run.answer = (f"I can't reach the HR tool service right now, so I can't safely check policy sources or your records. "
                      f"Please try again in a moment, or contact {HR_CONTACT}.")
        run.escalation = {"needed": True, "reason": "MCP tool service unavailable", "route": "People team"}
        run.step("guardrail", "Degraded mode: MCP unavailable", status="error", summary="no ungrounded answer is given when tools cannot be reached")

    async def _profile(self, run: Run, slots: dict, why: str) -> dict | None:
        eid = slots.get("employee_id")
        if not eid:
            self._clarify(run, "Which employee are you asking about? Select your employee in the picker or include your employee ID (for example E1001) so I can check your record.",
                          slots, "employee_id missing for a personalised request")
            return None
        res = await self._call(run, "lookup_employee_profile", {"employee_id": eid}, why)
        if not res["ok"]:
            if res.get("unavailable") or run.degraded:
                self._degrade(run)
            else:
                slots.pop("employee_id", None)
                self._clarify(run, f"I couldn't find an employee with ID '{eid}'. Employee IDs look like E1001 (this demo has E1001-E1015). Could you check it?",
                              slots, "unknown employee id")
            return None
        return res["data"]

    def _plan(self, run: Run, steps: list[str]) -> None:
        run.step("plan", f"Workflow for '{run.intent}'", status="ok", summary=" → ".join(steps))

    async def _propose_ticket(self, run: Run, eid: str, category: str, summary: str, details: str, priority: str = "normal") -> None:
        res = await self._call(run, "create_mock_hr_ticket", {"employee_id": eid, "category": category, "summary": summary, "details": details, "priority": priority},
                               "preview a mock ticket (nothing is created until the user confirms)")
        if res["ok"] and res["data"].get("status") == "pending_confirmation":
            aid = uuid.uuid4().hex[:8]
            args = {"employee_id": eid, "category": category, "summary": summary, "details": details, "priority": priority}
            self._pending[aid] = {"tool": "create_mock_hr_ticket", "arguments": args, "t": time.time()}
            for k in [k for k, v in self._pending.items() if time.time() - v["t"] > 1800]:
                self._pending.pop(k, None)
            run.pending.append({"action_id": aid, "tool": "create_mock_hr_ticket", "arguments": args, "requires_confirmation": True,
                                "description": f"Create a MOCK HR ticket ({category}): {summary}"})
            run.step("decision", "Action requires explicit user confirmation", status="ok", summary=f"ticket preview ready (action_id {aid}); nothing was created")

    async def _draft_email(self, run: Run, eid: str, recipient: str, purpose: str, details: list[str]) -> None:
        res = await self._call(run, "draft_hr_email", {"employee_id": eid, "recipient": recipient, "purpose": purpose, "details": details}, "draft (not send) a message")
        if res["ok"]:
            d = res["data"]
            run.drafts.append({"to": d["to"], "subject": d["subject"], "body": d["body"], "sent": d["sent"]})

    # ================================================================== workflows
    async def _pto_request(self, run: Run, slots: dict, cls: dict) -> None:
        if not slots.get("employee_id"):
            return self._clarify(run, "Which employee are you? Select your employee in the picker or include your employee ID (for example E1001) so I can check your PTO balance.", slots, "employee_id missing")
        if slots.get("days") is None:
            return self._clarify(run, "How many days of PTO would you like to take, and starting on which date?", slots, "number of days missing")
        self._plan(run, ["lookup_employee_profile", "check_pto_balance", "search_policy_documents", "check_policy_compliance", "draft_hr_email", "(create_mock_hr_ticket preview if an exception is needed)"])
        emp = await self._profile(run, slots, "identify the employee, manager, tenure and department")
        if emp is None:
            return
        eid, days, start = emp["employee_id"], float(slots["days"]), slots.get("start_date")
        bal = await self._call(run, "check_pto_balance", {"employee_id": eid, "days_requested": days}, "check available PTO against the request")
        queries = [f"PTO request notice period and manager approval for {days:g} days", "PTO accrual carryover short-notice exception negative balance"]
        if emp["department"] == "Finance":
            queries.append("Finance quarter-end blackout PTO")
        await self._retrieve(run, queries)
        comp = await self._call(run, "check_policy_compliance", {"employee_id": eid, "scenario": "pto_request", "start_date": start, "days": days},
                                "apply the written PTO rules (notice, balance, probation, blackout)")
        if run.degraded and not comp["ok"] and not bal["ok"]:
            return self._degrade(run)
        run.answer = self._answer_pto(run, emp, bal.get("data") if bal["ok"] else None, comp.get("data") if comp["ok"] else None, days, start)
        c = comp.get("data") or {}
        details = [f"Dates: {start or 'to be confirmed'} ({days:g} working day(s))"]
        if bal["ok"]:
            details.append(f"Available PTO balance: {bal['data']['available_days']:g} days")
        if any(x["status"] == "needs_approval" and x["rule"] == "notice_period" for x in c.get("checks", [])):
            details.append("This is a short-notice request; business reason: [please add]")
        if days >= 3:
            details.append("Coverage plan: [please add who covers urgent work]")
        await self._draft_email(run, eid, "manager", "pto_request", details)
        needs_exc = c.get("overall") == "needs_approval"
        if needs_exc:
            await self._propose_ticket(run, eid, "pto", f"PTO exception review: {days:g} day(s) from {start or 'TBD'}",
                                       "Checks needing approval: " + "; ".join(f"{x['rule']}: {x['detail']}" for x in c.get("checks", []) if x["status"] in ("needs_approval", "fail")))
        run.escalation = {"needed": needs_exc, "reason": "request needs an approval/exception outside the standard path" if needs_exc else None,
                          "route": "manager / People team" if needs_exc else None}
        run.step("decision", "Escalation decision", status="ok", summary=("escalate for exception review (via manager / People team)" if needs_exc else "no escalation: standard manager approval is enough"))

    async def _pto_balance(self, run: Run, slots: dict, cls: dict) -> None:
        if not slots.get("employee_id"):
            return self._clarify(run, "Which employee are you? Select your employee in the picker or include your employee ID (for example E1001).", slots, "employee_id missing")
        self._plan(run, ["check_pto_balance", "search_policy_documents"])
        bal = await self._call(run, "check_pto_balance", {"employee_id": slots["employee_id"]}, "read the PTO balance")
        if not bal["ok"]:
            if run.degraded:
                return self._degrade(run)
            slots.pop("employee_id", None)
            return self._clarify(run, f"I couldn't find an employee with ID '{slots.get('employee_id', '')}'. Employee IDs look like E1001 (E1001-E1015).", slots, "unknown employee id")
        await self._retrieve(run, ["PTO accrual rates carryover"], top_k=3)
        d = bal["data"]
        if not d["pto_eligible"]:
            run.answer = f"**Short answer:** You don't accrue PTO. {d['reason']} {_tag('POL-001', '2')}"
        else:
            run.answer = (f"**Short answer:** You have **{d['available_days']:g} PTO days** available as of {d['as_of']}.\n\n"
                          f"- Balance: {d['carryover_days']:g} carried over + {d['accrued_ytd_days']:g} accrued this year − {d['used_ytd_days']:g} used − {d['pending_days']:g} pending.\n"
                          f"- Your annual entitlement is {d['annual_entitlement_days']:g} days, accrued monthly by length of service {_tag('POL-001', '3')}.\n"
                          f"- Up to 5 unused days can carry over to next year, and carried-over days expire on March 31 {_tag('POL-001', '4')}.\n"
                          f"- Sick days are separate: you have {d['sick_days_remaining']:g} remaining {_tag('POL-001', '8')}.")

    async def _remote_work(self, run: Run, slots: dict, cls: dict) -> None:
        if not slots.get("employee_id"):
            return self._clarify(run, "Which employee are you? Select your employee in the picker or include your employee ID (for example E1001) so I can check eligibility.", slots, "employee_id missing")
        self._plan(run, ["lookup_employee_profile", "check_policy_compliance", "search_policy_documents (remote work + security + tax)", "get_policy_section", "draft_hr_email", "(create_mock_hr_ticket preview)"])
        emp = await self._profile(run, slots, "identify country, data-access level, tenure and manager")
        if emp is None:
            return
        eid, bd, start = emp["employee_id"], slots.get("business_days"), slots.get("start_date")
        country, state = slots.get("destination_country"), slots.get("destination_state")
        comp = await self._call(run, "check_policy_compliance", {"employee_id": eid, "scenario": "remote_work", "start_date": start, "business_days": bd,
                                                                 "destination_country": country, "destination_state": state},
                                "apply remote-work, security and approval rules")
        if not comp["ok"] and run.degraded:
            return self._degrade(run)
        international = bool(country and country.lower() not in {"united states", "pakistan", "united kingdom"}) or slots.get("destination_hint") == "international" \
            or bool(country and country != {"US": "United States", "PK": "Pakistan", "GB": "United Kingdom"}[emp["country"]])
        queries = ["temporary remote work from another country limit approvals notice",
                   "security review approved countries for Confidential and Restricted data access",
                   "tax payroll work location another state or country"]
        await self._retrieve(run, queries if (international or not state) else [queries[0].replace("country", "state"), queries[2]], top_k=4)
        sec = "5" if international or not state else "4"
        await self._call(run, "get_policy_section", {"doc_id": "POL-003", "section": sec}, "load the exact approval/limit section for citation")
        c = comp.get("data") or {}
        run.answer = self._answer_remote(run, emp, c, slots, international)
        dest = country or state or "[destination]"
        details = [f"Destination: {dest}", f"Planned duration: {bd if bd else '[weeks]'} business days", f"Start date: {start or '[date]'}",
                   "I understand the 20-business-day limit and the approval steps in the Remote and Flexible Work Policy (POL-003)."]
        await self._draft_email(run, eid, "manager", "remote_work_request", details)
        hard_stop = any(x["status"] == "fail" and x["rule"] in ("sanctioned_destination", "eligibility", "introductory_period") for x in c.get("checks", []))
        needs_exc = c.get("overall") in ("needs_approval", "not_compliant") and not hard_stop
        if needs_exc:
            await self._propose_ticket(run, eid, "remote_work", f"Remote work request: {dest} for {bd or '?'} business days",
                                       "Checks: " + "; ".join(f"{x['rule']}={x['status']}" for x in c.get("checks", [])))
        run.escalation = {"needed": needs_exc, "reason": ("exception path: " if c.get("overall") == "not_compliant" else "approvals required: ") + ", ".join(c.get("approvals_required", [])[:4]) if needs_exc else None,
                          "route": "manager → department VP → People → Tax/Legal" if needs_exc else None}
        run.step("decision", "Escalation decision", status="ok", summary=("escalate/approvals needed: " + ", ".join(c.get("approvals_required", [])[:4])) if needs_exc else "no escalation needed")

    async def _expense(self, run: Run, slots: dict, cls: dict) -> None:
        if not slots.get("employee_id"):
            return self._clarify(run, "Which employee are you? Select your employee in the picker or include your employee ID (for example E1001), because the answer depends on your work arrangement and tenure.", slots, "employee_id missing")
        item = slots.get("item")
        if not item:
            return self._clarify(run, "What is the expense for (for example a laptop, a home office chair, a hotel, a flight, or meals) and roughly how much was it?", slots, "expense item missing")
        self._plan(run, ["lookup_employee_profile", "search_policy_documents", "check_policy_compliance"])
        emp = await self._profile(run, slots, "check work arrangement, employment type and tenure for stipend eligibility")
        if emp is None:
            return
        await self._retrieve(run, [f"expense reimbursement policy {item.replace('_', ' ')}", "home office stipend equipment reimbursement approval limits"], top_k=4)
        comp = await self._call(run, "check_policy_compliance", {"employee_id": emp["employee_id"], "scenario": "expense", "item": item, "amount": slots.get("amount"), "nights": slots.get("nights"),
                                                                 "city": slots.get("city"), "flight_hours": slots.get("flight_hours"), "cabin_class": slots.get("cabin_class")},
                                "apply the expense rules for this item")
        if not comp["ok"]:
            return self._degrade(run) if run.degraded else self._clarify(run, "I couldn't evaluate that expense. Could you rephrase it?", slots, "compliance tool error")
        run.answer = self._answer_expense(run, emp, comp["data"], item, slots.get("amount"))
        c = comp["data"]
        run.escalation = {"needed": False, "reason": None, "route": None}
        run.step("decision", "Escalation decision", status="ok", summary="no escalation: decision follows directly from the expense policy" if c["overall"] != "needs_approval" else "approval needed from " + (c["approvals_required"][0] if c["approvals_required"] else "approver"))
        if c["overall"] == "compliant" and emp["employment_type"] != "contractor":
            await self._draft_email(run, emp["employee_id"], "hr", "expense_question", [f"Item: {item.replace('_', ' ')}", f"Amount: ${slots['amount']:g}" if slots.get("amount") else "Amount: [amount]", "Please confirm the reimbursement steps."])

    async def _benefits(self, run: Run, slots: dict, cls: dict) -> None:
        if not slots.get("employee_id"):
            return self._clarify(run, "Which employee are you? Select your employee in the picker or include your employee ID (for example E1001) so I can check your eligibility.", slots, "employee_id missing")
        self._plan(run, ["lookup_employee_profile", "lookup_benefits_status", "search_policy_documents"])
        emp = await self._profile(run, slots, "identify employment type and country")
        if emp is None:
            return
        ben = await self._call(run, "lookup_benefits_status", {"employee_id": emp["employee_id"]}, "read eligibility and current elections")
        await self._retrieve(run, [run.message, "benefits eligibility full-time part-time contractor"], top_k=4, doc_id="POL-006")
        b = ben.get("data") or {}
        elig, el = b.get("eligibility", {}), b.get("elections") or {}
        summ = re.sub(r"\s*\(POL-\d{3} §\d+\)", "", elig.get("summary", "Eligibility could not be determined."))
        lines = [f"**Short answer:** {summ} {_tag('POL-006', '2' if emp['country'] == 'US' else '9')}"]
        if el and el.get("status") != "not_eligible":
            parts = []
            if el.get("medical", {}).get("plan"):
                parts.append(f"medical: {el['medical']['plan']} ({el['medical']['coverage_tier'].replace('_', ' ')})")
            for k in ("dental", "vision"):
                if el.get(k):
                    parts.append(f"{k}: {el[k]}")
            if el.get("k401"):
                parts.append(f"401(k): {el['k401']['employee_pct']}% with {el['k401']['employer_match_pct']}% company match")
            if el.get("provident_fund"):
                parts.append(f"provident fund: {el['provident_fund']['employer_pct']}% employer contribution")
            if el.get("pension"):
                parts.append(f"pension: {el['pension']['employer_pct']}% employer contribution")
            lines.append("**Your current elections (mock HRIS):** " + "; ".join(parts) + ".")
        ev = self._ranked_evidence(run, 0.6)[:2]
        if ev:
            lines.append("**What the policy says**\n" + "\n".join(
                "- " + " ".join(pick_sentences(run.message + " " + " ".join(run.rewritten), c["text"], 2)) + f" {_tag(c['doc_id'], c['section_number'])}" for c in ev))
        lines.append("**Recommendations (not policy)**\n- Open enrollment runs Nov 1-15, and life-event changes must be filed within 30 days " + _tag("POL-006", "6") + ".\n- For plan-specific details contact benefits@northwind.example.")
        run.answer = "\n\n".join(lines)
        run.escalation = {"needed": False, "reason": None, "route": None}
        run.step("decision", "Escalation decision", status="ok", summary="answered from policy + mock benefits record; plan-specific questions go to the Benefits team")

    async def _hr_case(self, run: Run, slots: dict, cls: dict) -> None:
        self._plan(run, ["search_policy_documents (POL-008)", "get_policy_section (escalation rules)", "(create_mock_hr_ticket preview for Employee Relations)"])
        await self._retrieve(run, ["how to report harassment discrimination retaliation Employee Relations investigation"], top_k=4, doc_id="POL-008")
        secs = {}
        for s in ("4", "5", "6", "7"):
            r = await self._call(run, "get_policy_section", {"doc_id": "POL-008", "section": s}, f"load POL-008 §{s} for exact reporting/escalation wording")
            if r["ok"]:
                secs[s] = r["data"]["text"]
        if not secs:
            return self._degrade(run)
        run.step("decision", "Escalation decision", status="ok", summary="sensitive workplace matter → must be referred to Employee Relations; the assistant does not investigate or judge",
                 output={"policy": "POL-008 §7"})
        run.escalation = {"needed": True, "reason": "sensitive workplace issue (harassment/discrimination/retaliation/safety)", "route": "Employee Relations / Ethics Hotline"}
        channels = [ln.strip() for ln in secs.get("4", "").replace(" 2. ", "\n2. ").replace(" 3. ", "\n3. ").replace(" 4. ", "\n4. ").splitlines() if re.match(r"\s*\d\.", ln)]
        lines = ["I'm sorry you're dealing with this. I can't investigate or decide whether a policy was violated - matters like this must be handled by Employee Relations "
                 f"{_tag('POL-008', '7')}. If you or anyone is in immediate danger, call local emergency services first.",
                 "**How you can report it** " + _tag("POL-008", "4") + "\n" + "\n".join("- " + re.sub(r"^\s*\d\.\s*", "", c).rstrip(";.").replace("Their", "Your").replace("they trust", "you trust") for c in channels[:4])]
        s5 = [s for s in _split_sentences(secs.get("5", "")) if re.search(r"acknowledg|begins|completed", s, re.I)]
        if s5:
            lines.append("**What happens next** " + _tag("POL-008", "5") + "\n" + "\n".join("- " + s for s in s5[:3]))
        s6 = _split_sentences(secs.get("6", ""))
        if s6:
            lines.append(f"**Protection from retaliation:** {s6[0]} {_tag('POL-008', '6')}")
        eid = slots.get("employee_id")
        if eid:
            await self._propose_ticket(run, eid, "employee_relations", "Referral to Employee Relations (employee-initiated)",
                                       "Employee asked for help with a sensitive workplace matter and wants it referred to Employee Relations. Employee's message: " + run.message[:600], "high")
            lines.append("**Recommendation (not policy):** if you'd like, I can prepare a mock case summary for Employee Relations - review and confirm it below. Nothing is sent unless you confirm.")
        else:
            lines.append("**Recommendation (not policy):** you can use the anonymous Ethics Hotline, or tell me your employee ID if you want me to prepare a case summary for Employee Relations.")
        run.answer = "\n\n".join(lines)

    async def _policy_qa(self, run: Run, slots: dict, cls: dict) -> None:
        topics = cls["topics"]
        queries = [run.message] + [nlu.TOPICS[t][1] for t in topics[:3]] if len(topics) >= 2 else [run.message]
        self._plan(run, ["search_policy_documents" + (f" ×{len(queries)} (multi-topic: {', '.join(topics[:3])})" if len(queries) > 1 else "")])
        ev = await self._retrieve(run, queries, top_k=4)
        if ev is None:
            return self._degrade(run)
        ranked = self._ranked_evidence(run, 0.55)
        partial = (not ev["sufficient"]) and bool(topics) and ev["max_score"] >= settings.MIN_RELEVANCE and bool(ranked)
        if not ev["sufficient"] and not partial:
            run.step("guardrail", "Out-of-corpus / insufficient evidence", status="ok",
                     summary=f"max_score={ev['max_score']}, term_coverage={ev['term_coverage']} → refuse instead of guessing", output=ev)
            run.answer = ("I couldn't find anything in the Northwind HR policy documents that answers that, so I'd rather not guess. "
                          f"I can help with PTO, holidays, remote work, expenses, benefits, leave, security, onboarding, equipment, travel and conduct questions. "
                          f"For anything else, please contact {HR_CONTACT}.")
            run.escalation = {"needed": run.intent != "out_of_scope", "reason": "no policy evidence", "route": "People team"}
            return
        groups: dict[tuple[str, str], dict] = {}
        for c in ranked:
            groups.setdefault((c["doc_id"], c["section_number"]), c)
        picks = list(groups.values())[:3]
        lines = []
        if partial:
            miss = ", ".join(f"'{t}'" for t in ev.get("uncovered_terms", [])[:3]) or "part of your question"
            lines.append(f"**Heads-up:** the policy documents don't directly address {miss}. Here is the closest related policy content - please don't treat it as a ruling on that point.")
        elif ev.get("uncovered_terms") and ev["term_coverage"] < 0.75:
            lines.append(f"_Note: the policies don't specifically mention {', '.join(repr(t) for t in ev['uncovered_terms'][:2])}._")
        docs = {c["doc_id"] for c in picks}
        lines.append(("**What the policies say** (this touches more than one policy)" if len(docs) > 1 else "**What the policy says**"))
        vocab = run.message + " " + " ".join(run.rewritten)
        for i, c in enumerate(picks):
            lines.append(f"- {' '.join(pick_sentences(vocab, c['text'], 3 if i == 0 else 2))} {_tag(c['doc_id'], c['section_number'])}")
        lines.append("**Recommendation (not policy):** for a decision about your own situation, check with your HR Business Partner or " + HR_CONTACT + ".")
        run.answer = "\n\n".join(lines[:1] + ["\n".join(lines[1:-1])] + [lines[-1]]) if False else "\n\n".join([lines[0], "\n".join(lines[1:-1]), lines[-1]])
        run.escalation = {"needed": partial, "reason": "question only partly covered by policy" if partial else None, "route": "People team" if partial else None}
        run.step("decision", "Answer basis", status="ok", summary=f"{'partial' if partial else 'sufficient'} evidence from {len(picks)} section(s) across {len(docs)} document(s); no tools beyond RAG needed")

    async def _ambiguous(self, run: Run, slots: dict, cls: dict) -> None:
        msg = run.message.lower()
        resume = "pto_request" if _is(nlu._PTO, msg) else "remote_work" if _is(nlu._REMOTE, msg) else None
        if _is(nlu._PTO, msg):
            q = "Happy to help with time off. How many days would you like, and starting on what date? (You can also tell me your employee ID, for example E1001.)"
        elif _is(nlu._REMOTE, msg):
            q = "Happy to check that. Where would you like to work from (another state or country?), for how long, and starting when?"
        else:
            q = "I can help with HR policy and HR tasks such as PTO, holidays, remote work, expenses, benefits, leave, equipment and conduct. Could you tell me a bit more about what you need?"
        self._clarify(run, q, slots, cls["reasons"][0] if cls["reasons"] else "request too vague", resume=resume)

    # ================================================================== answer templates
    @staticmethod
    def _render_checks(checks: list[dict]) -> str:
        out = []
        for c in checks:
            out.append(f"- {STATUS_LABEL[c['status']]} - **{RULE_LABEL.get(c['rule'], c['rule'])}:** {c['detail']} {_tag(c['policy']['doc_id'], c['policy']['section'])}")
        return "\n".join(out)

    def _answer_pto(self, run: Run, emp: dict, bal: dict | None, comp: dict | None, days: float, start: str | None) -> str:
        when = f" starting {start}" if start else ""
        mgr = (emp.get("manager") or {}).get("name", "your manager")
        if comp is None:
            return f"I couldn't run the compliance checks. Please contact {HR_CONTACT}."
        o = comp["overall"]
        if o == "compliant":
            head = f"**Short answer:** Yes - a {days:g}-day PTO request{when} meets the policy requirements. It still needs {mgr}'s approval {_tag('POL-001', '6')}."
        elif o == "needs_approval":
            head = f"**Short answer:** You can request {days:g} day(s){when}, but it can't simply be approved as submitted - it needs extra approval (details below)."
        else:
            fails = [c for c in comp["checks"] if c["status"] == "fail"]
            head = f"**Short answer:** Not as requested - {fails[0]['detail']} {_tag(fails[0]['policy']['doc_id'], fails[0]['policy']['section'])}"
        parts = [head]
        if bal and bal.get("pto_eligible"):
            parts.append(f"**Your PTO balance:** {bal['available_days']:g} days available ({bal['carryover_days']:g} carryover + {bal['accrued_ytd_days']:g} accrued − {bal['used_ytd_days']:g} used − {bal['pending_days']:g} pending); "
                         f"after this request you'd have {bal['balance_after_request']:g} left {_tag('POL-001', '3')}.")
        parts.append("**Policy checks**\n" + self._render_checks(comp["checks"]))
        recs = [f"Submit the request in the HR system and tell {mgr} directly."]
        if any(c["rule"] == "notice_period" and c["status"] == "needs_approval" for c in comp["checks"]):
            recs.append("Because the notice is short, include a documented business reason; your manager decides whether to approve a short-notice request " + _tag("POL-001", "7") + ".")
        if days >= 3:
            recs.append("Share a short coverage plan (who handles urgent work) with your manager " + _tag("POL-001", "5") + ".")
        if any(c["rule"] == "balance" and c["status"] != "pass" for c in comp["checks"]):
            recs.append("Consider a shorter request, or ask the People team whether an advance of up to 2 unearned days is possible " + _tag("POL-001", "7") + ".")
        recs.append(f"I drafted an email to {mgr} (below). It has **not** been sent.")
        parts.append("**Recommendations (not policy)**\n" + "\n".join("- " + r for r in recs))
        return "\n\n".join(parts)

    def _answer_remote(self, run: Run, emp: dict, comp: dict, slots: dict, international: bool) -> str:
        dest = slots.get("destination_country") or slots.get("destination_state") or "another location"
        dur = f"{slots['business_days']} business days" if slots.get("business_days") else "that period"
        o = comp.get("overall")
        if o == "compliant":
            head = f"**Short answer:** Yes - working from {dest} for {dur} fits the policy, subject to the approvals below {_tag('POL-003', '5' if international else '4')}."
        elif o == "needs_approval":
            head = f"**Short answer:** Possibly - working from {dest} for {dur} is allowed in principle but needs approvals before you go; don't start until you have written approval {_tag('POL-003', '8')}."
        else:
            fails = [c for c in comp["checks"] if c["status"] == "fail"]
            head = f"**Short answer:** Not through the standard process - {fails[0]['detail']} {_tag(fails[0]['policy']['doc_id'], fails[0]['policy']['section'])}"
        parts = [head, "**Policy checks**\n" + self._render_checks(comp["checks"])]
        if comp.get("approvals_required"):
            parts.append("**Approvals / steps required:** " + "; ".join(comp["approvals_required"]) + " " + _tag("POL-003", "8"))
        ev = [c for c in self._ranked_evidence(run, 0.6) if c["doc_id"] in ("POL-004", "POL-003")][:2]
        if ev:
            parts.append("**Related policy**\n" + "\n".join(f"- {' '.join(pick_sentences(run.message + ' security tax approved countries', c['text'], 1))} {_tag(c['doc_id'], c['section_number'])}" for c in ev))
        recs = ["Talk to your manager and the People team before making travel plans."]
        if not (slots.get("destination_country") or slots.get("destination_state")):
            recs.append("Tell me the destination country or state and your start date, and I'll also check the approved-country, sanctions, tax and notice rules.")
        if o == "not_compliant" and any(c["rule"] == "duration_limit" and c["status"] == "fail" for c in comp["checks"]):
            recs.append("Consider a shorter stay (20 business days or fewer per year), or PTO / unpaid leave for the remainder, since long stays can create tax exposure " + _tag("POL-003", "5") + ".")
        recs.append("I drafted an email to your manager (below); it has **not** been sent.")
        parts.append("**Recommendations (not policy)**\n" + "\n".join("- " + r for r in recs))
        return "\n\n".join(parts)

    def _answer_expense(self, run: Run, emp: dict, comp: dict, item: str, amount: float | None) -> str:
        label = item.replace("_", " ")
        o, reimb = comp["overall"], comp.get("reimbursable_amount")
        fails = [c for c in comp["checks"] if c["status"] == "fail"]
        if o == "not_compliant" and fails:
            head = f"**Short answer:** No - {fails[0]['detail']} {_tag(fails[0]['policy']['doc_id'], fails[0]['policy']['section'])}"
        elif o == "needs_approval":
            amt = f" (reimbursable: ${reimb:g})" if reimb is not None and amount else ""
            head = f"**Short answer:** Partly / with approval - see the checks below{amt}."
        else:
            amt = f" up to ${reimb:g}" if reimb else ""
            head = f"**Short answer:** Yes - a {label} expense is reimbursable{amt} under the policy."
        parts = [head, "**Policy checks**\n" + self._render_checks(comp["checks"])]
        steps = list(comp.get("approvals_required", [])) + list(comp.get("notes", []))
        if steps:
            parts.append("**Steps**\n" + "\n".join("- " + s for s in steps))
        return "\n\n".join(parts)

    # ================================================================== LLM helpers
    async def _llm_intent(self, run: Run, fallback: str) -> str:
        try:
            d = await self.llm.complete_json([
                {"role": "system", "content": "Classify the HR request. Reply JSON {\"intent\": one of pto_request, pto_balance, remote_work, expense, benefits, hr_case, policy_qa, ambiguous, out_of_scope}."},
                {"role": "user", "content": run.message}])
            if d.get("intent") in {"pto_request", "pto_balance", "remote_work", "expense", "benefits", "hr_case", "policy_qa", "ambiguous", "out_of_scope"}:
                run.llm_used["intent"] = True
                run.step("intent", "LLM intent fallback", status="ok", summary=f"LLM proposed '{d['intent']}' for a low-confidence request")
                return d["intent"]
        except LLMError as e:
            run.step("error", "LLM intent fallback failed", status="error", summary=str(e)[:120])
        return fallback

    async def _llm_rewrite(self, run: Run) -> None:
        """Optional: let the LLM polish the grounded draft. Rejected (template kept) if it breaks grounding rules."""
        if not (self.llm.configured and run.answer and not run.needs_clarification and not run.degraded and CITE_RE.search(run.answer)):
            return
        evidence = [{"cite": _tag(c["doc_id"], c["section_number"]), "text": c["text"]} for c in self._ranked_evidence(run, 0.5)[:6]]
        facts = {"tool_results": {k: v for k, v in run.results.items() if k not in ("search_policy_documents", "get_policy_section")}, "evidence": evidence}
        sys_prompt = ("You are a careful HR policy assistant. Rewrite the DRAFT into a clear, concise answer (max 220 words). Rules: use ONLY facts in DRAFT, TOOL_RESULTS and EVIDENCE; "
                      "cite policy facts as [POL-xxx §n] using only citations that appear there; keep policy facts separate from a final 'Recommendations (not policy)' section; "
                      "do not add numbers that are not in the inputs; never claim an action was taken that was not (nothing is sent; tickets need confirmation).")
        try:
            out = await self.llm.complete([{"role": "system", "content": sys_prompt},
                                           {"role": "user", "content": f"QUESTION: {run.message}\n\nDRAFT:\n{run.answer}\n\nDATA:\n{json.dumps(facts)[:9000]}"}], max_tokens=600)
        except LLMError as e:
            run.step("error", "LLM synthesis failed - template answer kept", status="error", summary=str(e)[:120])
            return
        ok, why = self._validate_llm_answer(run, out)
        if ok:
            run.answer, run.llm_used["synthesis"] = out.strip(), True
            run.step("synthesis", "LLM-polished answer accepted", status="ok", summary="citations and numbers validated against evidence")
        else:
            run.step("guardrail", "LLM answer rejected - grounded template kept", status="ok", summary=why)

    def _validate_llm_answer(self, run: Run, text: str) -> tuple[bool, str]:
        allowed_cites = {(c["doc_id"], c["section_number"]) for c in run.evidence.values()} | set(CITE_RE.findall(run.answer))
        found = CITE_RE.findall(text)
        if not found:
            return False, "no citations in LLM answer"
        bad = [f for f in found if f not in allowed_cites]
        if bad:
            return False, f"LLM cited sections that were not retrieved: {bad[:2]}"
        corpus = run.message + " " + run.answer + " " + json.dumps(run.results) + " " + " ".join(c["text"] for c in run.evidence.values())
        known = {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", corpus)}
        stripped = CITE_RE.sub("", text)
        unknown = [n for n in re.findall(r"\d[\d,]*(?:\.\d+)?", stripped) if n.replace(",", "") not in known and float(n.replace(",", "")) > 3]
        if unknown:
            return False, f"LLM introduced numbers not found in the evidence: {unknown[:3]}"
        return True, "ok"

    # ================================================================== citations + response
    async def _finalize_citations(self, run: Run) -> list[dict]:
        run.answer = re.sub(r"\((POL-\d{3}) §(\d+)\)", r"[\1 §\2]", run.answer)
        if run.answer and not run.needs_clarification:
            await self._llm_rewrite(run)
        cited: list[tuple[str, str]] = []
        for m in CITE_RE.finditer(run.answer):
            key = (m.group(1), m.group(2))
            if key not in cited:
                cited.append(key)
        out = []
        for doc, sec in cited:
            cands = [c for c in run.evidence.values() if c["doc_id"] == doc and c["section_number"] == sec]
            chunk = max(cands, key=lambda c: c["score"]) if cands else None
            if chunk is None and not run.degraded:
                res = await self._call(run, "get_policy_section", {"doc_id": doc, "section": sec}, f"load {doc} §{sec} so the citation has a supporting snippet")
                if res["ok"]:
                    d = res["data"]
                    chunk = {"chunk_id": f"{doc}#s{sec}", "doc_id": doc, "title": d["title"], "section": d["section"], "section_number": sec, "source_file": d["source_file"],
                             "snippet": re.sub(r"\s+", " ", d["text"])[:300], "text": d["text"]}
                    run.evidence[chunk["chunk_id"]] = {**chunk, "score": 0.0}
            if chunk is None:
                run.answer = run.answer.replace(_tag(doc, sec), "")
                run.step("guardrail", "Removed unverifiable citation", status="ok", summary=f"{doc} §{sec} had no retrieved evidence")
                continue
            sn = chunk["snippet"]
            # prefer the sentence most related to the question as the supporting snippet
            best = pick_sentences(run.message, chunk["text"], 1)
            out.append({"doc_id": doc, "title": chunk["title"], "section": chunk["section"], "section_number": sec, "source_file": chunk["source_file"],
                        "snippet": (best[0] if best else sn)[:320]})
        return out

    def _response(self, run: Run, citations: list[dict]) -> dict:
        run.step("synthesis", "Final answer assembled", status="ok",
                 summary=f"{len(citations)} citation(s); tools called: {', '.join(dict.fromkeys(run.tools_called)) or 'none'}; "
                         f"escalation={'yes' if run.escalation['needed'] else 'no'}; clarification={'yes' if run.needs_clarification else 'no'}")
        return {"answer": run.answer, "intent": run.intent, "citations": citations, "trace": run.trace, "tools_called": run.tools_called,
                "pending_actions": run.pending, "drafts": run.drafts, "escalation": run.escalation, "needs_clarification": run.needs_clarification,
                "state": run.state, "llm_used": run.llm_used, "evidence": run.query_evidence,
                "latency_ms": round((time.perf_counter() - run.t0) * 1000, 1)}


def _is(pattern: re.Pattern, text: str) -> bool:
    return bool(pattern.search(text))
