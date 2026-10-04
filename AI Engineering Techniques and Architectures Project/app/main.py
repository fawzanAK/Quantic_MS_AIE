"""FastAPI web app: chat UI, /chat, /confirm, /health, /tools, plus demo helpers.

The app owns an MCP client (stdio subprocess by default, or MCP_SERVER_URL for a separate service) and an agent.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import settings
from app.agent import HRAgent
from app.llm import LLM
from app.mcp_client import MCPClient

STATIC = Path(__file__).parent / "static"
VERSION = "1.0.0"

DEMO_TASKS = [
    {"id": "pto", "title": "Task 1 - PTO request guidance", "employee_id": "E1001",
     "prompt": "Can I take 3 days of PTO next week?",
     "expected_tools": ["lookup_employee_profile", "check_pto_balance", "search_policy_documents", "check_policy_compliance", "draft_hr_email", "create_mock_hr_ticket (preview)"],
     "what_to_notice": "Balance is sufficient, but 2 business days of notice is short of the 10 required for a 3-day request, so the agent flags a manager exception, drafts an email, and previews a mock ticket that needs your confirmation."},
    {"id": "remote", "title": "Task 2 - Remote work eligibility (multi-document)", "employee_id": "E1004",
     "prompt": "Can I work remotely from Spain for six weeks starting November 16?",
     "expected_tools": ["lookup_employee_profile", "check_policy_compliance", "search_policy_documents x3", "get_policy_section", "draft_hr_email", "create_mock_hr_ticket (preview)"],
     "what_to_notice": "Combines POL-003 (remote work), POL-004 (security / approved countries) and tax rules: Spain is an approved country, but 30 business days exceeds the 20-day limit, so only an exception path exists."},
    {"id": "expense", "title": "Bonus - Expense compliance", "employee_id": "E1006", "prompt": "Can I expense a home office chair?",
     "expected_tools": ["lookup_employee_profile", "search_policy_documents", "check_policy_compliance"], "what_to_notice": "Omar is fully remote but still in the 90-day introductory period, so the stipend is not available yet."},
    {"id": "hr_case", "title": "Bonus - HR case triage (escalation)", "employee_id": "E1003", "prompt": "My manager keeps making inappropriate comments about me.",
     "expected_tools": ["search_policy_documents", "get_policy_section", "create_mock_hr_ticket (preview)"], "what_to_notice": "The assistant does not judge the case; it explains reporting channels and offers a mock Employee Relations referral that needs confirmation."},
    {"id": "guardrail", "title": "Bonus - Out-of-scope guardrail", "employee_id": "E1001", "prompt": "What is the weather in Paris today?",
     "expected_tools": ["search_policy_documents"], "what_to_notice": "Retrieval evidence is too weak, so the assistant refuses to guess and redirects."},
]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    employee_id: str | None = Field(default=None, max_length=12)
    state: dict | None = None


class ActionRequest(BaseModel):
    action_id: str = Field(min_length=1, max_length=64)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.started = time.time()
        t0 = time.perf_counter()
        mcp = MCPClient()
        await mcp.start()
        app.state.startup_ms = round((time.perf_counter() - t0) * 1000)
        app.state.mcp = mcp
        app.state.agent = HRAgent(mcp, LLM())
        yield
        await mcp.close()

    app = FastAPI(title="Northwind HR Agentic Assistant", version=VERSION, lifespan=lifespan,
                  description="Agentic RAG + MCP demo for a fictional company (all data synthetic).")

    @app.get("/health")
    async def health():
        mcp: MCPClient = app.state.mcp
        m = await mcp.health()
        probe = {"ok": False}
        if m["connected"]:
            r = await mcp.call_tool("search_policy_documents", {"query": "PTO", "top_k": 1})
            probe = {"ok": r["ok"], "latency_ms": r["latency_ms"], **({"index": r["data"].get("index")} if r["ok"] else {"error": r["error"]})}
        llm: LLM = app.state.agent.llm
        return {"status": "ok" if (m["connected"] and probe["ok"]) else "degraded",
                "app": {"name": "northwind-hr-agent", "version": VERSION, "uptime_s": round(time.time() - app.state.started, 1),
                        "mcp_startup_ms": app.state.startup_ms, "reference_date": settings.today().isoformat()},
                "mcp": {**m, "probe_search_policy_documents": probe},
                "llm": {"configured": llm.configured, "model": llm.model if llm.configured else None,
                        "mode": "LLM-polished answers (validated)" if llm.configured else "deterministic grounded answers (no LLM key set)"}}

    @app.post("/chat")
    async def chat(req: ChatRequest):
        return await app.state.agent.handle(req.message, req.employee_id, req.state)

    @app.post("/confirm")
    async def confirm(req: ActionRequest):
        out = await app.state.agent.confirm(req.action_id)
        if not out["ok"] and "Unknown" in str(out.get("error")):
            raise HTTPException(404, out["error"])
        return out

    @app.post("/cancel")
    async def cancel(req: ActionRequest):
        return app.state.agent.cancel(req.action_id)

    @app.get("/tools")
    async def tools():
        """Tool discovery: exactly what the MCP server advertises to the agent."""
        mcp: MCPClient = app.state.mcp
        return {"transport": mcp.transport, "tools": mcp.tools}

    @app.get("/employees")
    async def employees():
        import json
        data = json.loads((settings.MOCK_DIR / "employees.json").read_text())["employees"]
        return [{"employee_id": e["employee_id"], "name": e["name"], "role": e["role"], "office": e["office"], "employment_type": e["employment_type"]} for e in data]

    @app.get("/demo-tasks")
    async def demo_tasks():
        return {"reference_date": settings.today().isoformat(), "tasks": DEMO_TASKS}

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
