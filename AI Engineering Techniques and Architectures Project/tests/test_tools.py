import json

import settings
from mcp_server import tools


def checks(res):
    return {c["rule"]: c["status"] for c in res["checks"]}


def test_pto_short_notice_needs_approval():
    r = tools.check_policy_compliance("E1001", "pto_request", start_date="2026-10-05", days=3)
    assert r["overall"] == "needs_approval" and checks(r)["notice_period"] == "needs_approval" and checks(r)["balance"] == "pass"


def test_pto_insufficient_balance_fails():
    r = tools.check_policy_compliance("E1004", "pto_request", start_date="2026-12-01", days=6)
    assert checks(r)["balance"] == "fail" and r["overall"] == "not_compliant"


def test_pto_intro_period_needs_people_approval():
    r = tools.check_policy_compliance("E1006", "pto_request", start_date="2026-10-12", days=1)
    assert checks(r)["introductory_period"] == "needs_approval"


def test_finance_quarter_end_blackout():
    r = tools.check_policy_compliance("E1004", "pto_request", start_date="2026-12-28", days=2)
    assert checks(r)["finance_quarter_end_blackout"] == "needs_approval"


def test_contractor_has_no_pto():
    assert tools.check_pto_balance("E1009")["pto_eligible"] is False
    assert tools.check_policy_compliance("E1009", "pto_request", days=1)["overall"] == "not_compliant"


def test_remote_six_weeks_exceeds_limit_but_spain_is_approved():
    r = tools.check_policy_compliance("E1004", "remote_work", start_date="2026-11-16", business_days=30, destination_country="Spain")
    c = checks(r)
    assert c["duration_limit"] == "fail" and c["approved_country"] == "pass" and r["overall"] == "not_compliant"


def test_remote_restricted_country_and_sanctions():
    assert checks(tools.check_policy_compliance("E1007", "remote_work", business_days=10, destination_country="Thailand"))["approved_country"] == "fail"
    assert checks(tools.check_policy_compliance("E1001", "remote_work", business_days=5, destination_country="Iran"))["sanctioned_destination"] == "fail"


def test_remote_not_allowed_during_intro_period():
    assert checks(tools.check_policy_compliance("E1006", "remote_work", business_days=5, destination_state="Texas"))["introductory_period"] == "fail"


def test_expense_rules():
    assert tools.check_policy_compliance("E1002", "expense", item="laptop", amount=1200)["overall"] == "not_compliant"
    assert tools.check_policy_compliance("E1006", "expense", item="chair", amount=300)["overall"] == "not_compliant"  # intro period
    r = tools.check_policy_compliance("E1001", "expense", item="chair", amount=350)  # hybrid: $200 stipend
    assert r["reimbursable_amount"] == 200
    assert tools.check_policy_compliance("E1005", "expense", item="chair", amount=100)["overall"] == "not_compliant"  # office-based


def test_benefits_eligibility():
    assert tools.lookup_benefits_status("E1005")["eligibility"]["medical"] is False
    assert tools.lookup_benefits_status("E1001")["eligibility"]["k401_match"] is True
    assert tools.lookup_benefits_status("E1009")["elections"]["status"] == "not_eligible"


def test_unknown_employee_returns_structured_error():
    r = tools.lookup_employee_profile("E9999")
    assert r["ok"] is False and r["error"]["code"] == "EMPLOYEE_NOT_FOUND"


def test_ticket_requires_confirmation_and_persists_only_when_confirmed():
    path = settings.RUNTIME_DIR / "tickets_created.json"
    before = json.loads(path.read_text()) if path.exists() else []
    preview = tools.create_mock_hr_ticket("E1001", "pto", "test")
    assert preview["created"] is False and preview["status"] == "pending_confirmation"
    assert (json.loads(path.read_text()) if path.exists() else []) == before
    done = tools.create_mock_hr_ticket("E1001", "pto", "test", confirmed=True)
    assert done["created"] is True and done["ticket"]["mock"] is True
    assert len(json.loads(path.read_text())) == len(before) + 1


def test_email_is_draft_only():
    d = tools.draft_hr_email("E1001", "manager", "pto_request", ["3 days"])
    assert d["sent"] is False and "DRAFT" in d["note"]
