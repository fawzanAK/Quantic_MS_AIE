"""MCP integration: discovery + real tool calls over the stdio transport (what CI gates on)."""
import os

import pytest

from app.mcp_client import MCPClient

EXPECTED = {"search_policy_documents", "get_policy_section", "lookup_employee_profile", "check_pto_balance",
            "lookup_benefits_status", "create_mock_hr_ticket", "draft_hr_email", "check_policy_compliance"}


@pytest.fixture
async def client():
    c = MCPClient(env={"APP_TODAY": os.environ["APP_TODAY"], "RUNTIME_DIR": os.environ["RUNTIME_DIR"]})
    assert await c.start(), c.last_error
    yield c
    await c.close()


async def test_tool_discovery(client):
    assert EXPECTED <= set(client.tool_names) and len(client.tool_names) >= 5
    assert all(t["input_schema"].get("properties") for t in client.tools)


async def test_rag_tool_call_via_mcp(client):
    r = await client.call_tool("search_policy_documents", {"query": "sick leave days", "top_k": 3})
    assert r["ok"] and r["data"]["results"][0]["doc_id"] in {"POL-007", "POL-001"}


async def test_mock_data_tool_call_via_mcp(client):
    r = await client.call_tool("check_pto_balance", {"employee_id": "E1001", "days_requested": 3})
    assert r["ok"] and r["data"]["available_days"] == 7.75 and r["data"]["sufficient_balance"] is True


async def test_tool_error_is_reported_not_raised(client):
    r = await client.call_tool("lookup_employee_profile", {"employee_id": "E0000"})
    assert r["ok"] is False and "No employee" in r["error"]


async def test_ping_health(client):
    h = await client.health()
    assert h["connected"] and h["transport"] == "stdio" and h["tool_count"] >= 8
