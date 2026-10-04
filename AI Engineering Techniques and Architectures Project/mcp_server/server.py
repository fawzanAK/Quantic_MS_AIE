"""MCP server: exposes the HR tools over the Model Context Protocol.

Transports
  * stdio (default)          - spawned as a subprocess by the web app's MCP client (single free-tier service)
  * streamable-http          - `python -m mcp_server.server --transport streamable-http --port 8001`
                               (deploy separately and point the app at it with MCP_SERVER_URL=http://host:8001/mcp)

IMPORTANT for stdio: never print to stdout (it is the protocol channel). Logging goes to stderr.
"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from mcp_server import tools as impl

logging.basicConfig(level=logging.WARNING, stream=sys.stderr, format="[mcp-server] %(message)s")

mcp = FastMCP(
    "northwind-hr",
    instructions=(
        "HR policy + operations tools for the fictional company Northwind Analytics. All employee data is synthetic. "
        "Use search_policy_documents / get_policy_section for policy evidence, the lookup_/check_ tools for mock "
        "structured data, and create_mock_hr_ticket / draft_hr_email for mock actions (tickets need confirmed=true)."
    ),
)

EmployeeId = Annotated[str, Field(description="Synthetic employee id such as E1001")]


@mcp.tool()
def search_policy_documents(
    query: Annotated[str, Field(description="Natural-language question or keywords")],
    top_k: Annotated[int, Field(description="Number of chunks to return (1-10)", ge=1, le=10)] = 5,
    doc_id: Annotated[str | None, Field(description="Optional filter, e.g. POL-001")] = None,
) -> dict[str, Any]:
    """Hybrid (FAISS dense + TF-IDF) search over the HR policy corpus. Returns ranked chunks with doc id, title,
    section, score, snippet and full text, plus an `evidence` block (max_score, term_coverage, sufficient)."""
    return impl.search_policy_documents(query, top_k, doc_id)


@mcp.tool()
def get_policy_section(
    doc_id: Annotated[str, Field(description="Policy id, e.g. POL-003")],
    section: Annotated[str, Field(description="Section number ('5') or part of its heading ('Carryover')")],
) -> dict[str, Any]:
    """Return the full text of one policy section (exact citation target)."""
    return impl.get_policy_section(doc_id, section)


@mcp.tool()
def lookup_employee_profile(employee_id: EmployeeId) -> dict[str, Any]:
    """Look up a synthetic employee profile: role, department, office/country, employment type, start date,
    tenure, introductory-period status, work arrangement, data-access level and manager."""
    return impl.lookup_employee_profile(employee_id)


@mcp.tool()
def check_pto_balance(
    employee_id: EmployeeId,
    days_requested: Annotated[float | None, Field(description="Optional: days the employee wants to take")] = None,
) -> dict[str, Any]:
    """Return PTO entitlement, carryover, accrued, used, pending and available days (mock HRIS data); if
    days_requested is given, also whether the balance is sufficient."""
    return impl.check_pto_balance(employee_id, days_requested)


@mcp.tool()
def lookup_benefits_status(employee_id: EmployeeId) -> dict[str, Any]:
    """Return an employee's benefits eligibility (derived from employment type/hours/country) and mock elections."""
    return impl.lookup_benefits_status(employee_id)


@mcp.tool()
def create_mock_hr_ticket(
    employee_id: EmployeeId,
    category: Annotated[str, Field(description="pto, remote_work, expense, benefits, equipment, payroll, employee_relations, leave or other")],
    summary: Annotated[str, Field(description="One-line ticket summary")],
    details: Annotated[str, Field(description="Longer description")] = "",
    priority: Annotated[str, Field(description="low | normal | high")] = "normal",
    confirmed: Annotated[bool, Field(description="MUST be false until the human user explicitly approves. When false only a preview is returned and nothing is stored.")] = False,
) -> dict[str, Any]:
    """MOCK action: create an HR ticket. Irreversible-style actions are gated - without confirmed=true this returns
    a preview and writes nothing."""
    return impl.create_mock_hr_ticket(employee_id, category, summary, details, priority, confirmed)


@mcp.tool()
def draft_hr_email(
    employee_id: EmployeeId,
    recipient: Annotated[str, Field(description="manager | hr | it")],
    purpose: Annotated[str, Field(description="pto_request | remote_work_request | expense_question | general")],
    details: Annotated[list[str] | None, Field(description="Bullet points to include")] = None,
) -> dict[str, Any]:
    """Draft (never send) an email from the employee to their manager, HR or IT."""
    return impl.draft_hr_email(employee_id, recipient, purpose, details)


@mcp.tool()
def check_policy_compliance(
    employee_id: EmployeeId,
    scenario: Annotated[str, Field(description="pto_request | remote_work | expense")],
    start_date: Annotated[str | None, Field(description="ISO date YYYY-MM-DD (pto_request / remote_work)")] = None,
    days: Annotated[float | None, Field(description="PTO working days requested (pto_request)")] = None,
    destination_country: Annotated[str | None, Field(description="Country name (remote_work)")] = None,
    destination_state: Annotated[str | None, Field(description="US state name (remote_work, domestic)")] = None,
    business_days: Annotated[int | None, Field(description="Length of the remote stay in business days (remote_work)")] = None,
    item: Annotated[str | None, Field(description="laptop | chair | desk | home_office | hotel | meal | airfare | client_entertainment | other (expense)")] = None,
    amount: Annotated[float | None, Field(description="Amount in USD (expense)")] = None,
    nights: Annotated[int | None, Field(description="Hotel nights (expense)")] = None,
    city: Annotated[str | None, Field(description="City (expense: hotel)")] = None,
    flight_hours: Annotated[float | None, Field(description="Flight duration in hours (expense: airfare)")] = None,
    cabin_class: Annotated[str | None, Field(description="economy | premium economy | business | first (expense: airfare)")] = None,
) -> dict[str, Any]:
    """Rule-based compliance check that encodes the written policies. Returns overall status
    (compliant | needs_approval | not_compliant), per-rule checks each citing a policy section, and the approvals required."""
    return impl.check_policy_compliance(employee_id, scenario, start_date, days, destination_country, destination_state, business_days,
                                        item, amount, nights, city, flight_hours, cabin_class)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Northwind HR MCP server")
    ap.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8001)
    args = ap.parse_args(argv)
    impl._index()  # warm the index before serving (builds it if missing)
    if args.transport == "streamable-http":
        mcp.settings.host, mcp.settings.port = args.host, args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
