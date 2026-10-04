"""App-start smoke tests: the FastAPI app boots, spawns the MCP server, and serves /health and /chat."""
from fastapi.testclient import TestClient

from app.main import create_app


def test_app_starts_and_health_reports_mcp():
    with TestClient(create_app()) as c:
        h = c.get("/health").json()
        assert h["status"] == "ok"
        assert h["mcp"]["connected"] and h["mcp"]["tool_count"] >= 5 and h["mcp"]["probe_search_policy_documents"]["ok"]
        assert c.get("/").status_code == 200
        names = {t["name"] for t in c.get("/tools").json()["tools"]}
        assert "search_policy_documents" in names


def test_chat_endpoint_contract_and_confirmation_flow():
    with TestClient(create_app()) as c:
        r = c.post("/chat", json={"message": "Can I take 3 days of PTO next week?", "employee_id": "E1001"}).json()
        assert {"answer", "citations", "trace", "pending_actions", "intent"} <= set(r)
        assert r["citations"] and r["trace"]
        aid = r["pending_actions"][0]["action_id"]
        ok = c.post("/confirm", json={"action_id": aid}).json()
        assert ok["ok"] and ok["result"]["ticket"]["mock"] is True
        assert c.post("/confirm", json={"action_id": aid}).status_code == 404


def test_input_validation():
    with TestClient(create_app()) as c:
        assert c.post("/chat", json={"message": ""}).status_code == 422
        assert c.post("/chat", json={"message": "x" * 3000}).status_code == 422


def test_demo_tasks_and_employees_listed():
    with TestClient(create_app()) as c:
        assert len(c.get("/demo-tasks").json()["tasks"]) >= 2
        assert len(c.get("/employees").json()) == 15
