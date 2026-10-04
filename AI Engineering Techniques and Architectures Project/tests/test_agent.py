import json
import os

import httpx
import pytest

import settings
from app.agent import HRAgent
from app.llm import LLM
from app.mcp_client import MCPClient


@pytest.fixture
async def client():
    c = MCPClient(env={"APP_TODAY": os.environ["APP_TODAY"], "RUNTIME_DIR": os.environ["RUNTIME_DIR"]})
    assert await c.start(), c.last_error
    yield c
    await c.close()


@pytest.fixture
def agent(client):
    return HRAgent(client)


async def test_pto_workflow_calls_expected_tools_and_cites(agent):
    r = await agent.handle("Can I take 3 days of PTO next week?", "E1001")
    for t in ("lookup_employee_profile", "check_pto_balance", "search_policy_documents", "check_policy_compliance", "draft_hr_email"):
        assert t in r["tools_called"]
    assert r["citations"] and all(c["snippet"] for c in r["citations"])
    assert "short" in r["answer"].lower() or "notice" in r["answer"].lower()
    assert r["drafts"] and r["drafts"][0]["sent"] is False
    assert any(s["type"] == "plan" for s in r["trace"]) and all("summary" in s for s in r["trace"])


async def test_remote_workflow_is_multi_document(agent):
    r = await agent.handle("Can I work remotely from Spain for six weeks starting November 16?", "E1004")
    assert {"POL-003", "POL-004"} <= {c["doc_id"] for c in r["citations"]}
    assert r["escalation"]["needed"]


async def test_ticket_is_never_created_without_confirmation(agent):
    path = settings.RUNTIME_DIR / "tickets_created.json"
    n0 = len(json.loads(path.read_text())) if path.exists() else 0
    r = await agent.handle("Can I take 3 days of PTO next week?", "E1001")
    assert r["pending_actions"] and (len(json.loads(path.read_text())) if path.exists() else 0) == n0
    out = await agent.confirm(r["pending_actions"][0]["action_id"])
    assert out["ok"] and len(json.loads(path.read_text())) == n0 + 1
    assert (await agent.confirm(r["pending_actions"][0]["action_id"]))["ok"] is False  # single use


async def test_missing_employee_id_asks_for_clarification(agent):
    r = await agent.handle("Can I take 3 days off next week?")
    assert r["needs_clarification"] and r["tools_called"] == []


async def test_clarification_followup_completes_the_task(agent):
    r1 = await agent.handle("I need some time off", "E1001")
    assert r1["needs_clarification"] and r1["state"]
    r2 = await agent.handle("2 days starting October 20", "E1001", r1["state"])
    assert r2["intent"] == "pto_request" and not r2["needs_clarification"] and "check_pto_balance" in r2["tools_called"]


async def test_unknown_employee_id(agent):
    r = await agent.handle("How many PTO days do I have left?", "E9999")
    assert r["needs_clarification"] and "couldn't find" in r["answer"]


async def test_out_of_scope_is_refused(agent):
    r = await agent.handle("What is the weather in Paris today?", "E1001")
    assert r["citations"] == [] and "couldn't find" in r["answer"]


async def test_hr_case_escalates_without_judging(agent):
    r = await agent.handle("My manager keeps making inappropriate comments about me", "E1003")
    assert r["escalation"]["needed"] and "Employee Relations" in r["answer"] and r["pending_actions"]
    assert any(c["doc_id"] == "POL-008" for c in r["citations"])


async def test_tool_availability_ablation_is_respected(client):
    a = HRAgent(client, allowed_tools={"search_policy_documents"})
    r = await a.handle("Can I take 3 days of PTO next week?", "E1001")
    assert "check_pto_balance" not in r["tools_called"]
    assert any(s["status"] == "skipped" for s in r["trace"])


async def test_graceful_failure_when_mcp_is_unreachable():
    dead = MCPClient(url="http://127.0.0.1:9/mcp")
    a = HRAgent(dead)
    r = await a.handle("Can I take 3 days of PTO next week?", "E1001")
    assert "can't reach" in r["answer"] and r["escalation"]["needed"]
    await dead.close()


def _llm(text):
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})
    return LLM(api_key="test", base_url="http://llm.test/v1", transport=httpx.MockTransport(handler))


async def test_llm_answer_with_valid_citations_is_accepted(client):
    good = "Short answer: a 3-day request needs 10 business days of notice [POL-001 §5]. Recommendations (not policy): ask your manager."
    r = await HRAgent(client, _llm(good)).handle("Can I take 3 days of PTO next week?", "E1001")
    assert r["llm_used"]["synthesis"] and r["answer"].startswith("Short answer: a 3-day")


async def test_llm_answer_with_invented_number_is_rejected(client):
    bad = "You get 99 days of PTO [POL-001 §5]."
    r = await HRAgent(client, _llm(bad)).handle("Can I take 3 days of PTO next week?", "E1001")
    assert not r["llm_used"]["synthesis"] and "99" not in r["answer"]


async def test_llm_answer_citing_unretrieved_section_is_rejected(client):
    bad = "See [POL-016 §9] for details [POL-001 §5]."
    r = await HRAgent(client, _llm(bad)).handle("Can I take 3 days of PTO next week?", "E1001")
    assert not r["llm_used"]["synthesis"]
