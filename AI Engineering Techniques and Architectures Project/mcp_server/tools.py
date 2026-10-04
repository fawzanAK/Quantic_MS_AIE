"""Business logic behind the MCP tools (pure Python, no MCP imports -> easy to unit test).

All employee data is SYNTHETIC (mock_data/*.json). Mutating operations are mocks and require explicit confirmation.
"""
from __future__ import annotations

import datetime as dt
import json
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

import settings
from rag.index import PolicyIndex

# ----------------------------------------------------------------------------- data access
_lock = threading.Lock()


@lru_cache(maxsize=1)
def _index() -> PolicyIndex:
    return PolicyIndex.load_or_build()


@lru_cache(maxsize=1)
def _data() -> dict[str, Any]:
    def load(name: str, key: str):
        return json.loads((settings.MOCK_DIR / name).read_text(encoding="utf-8"))[key]

    return {
        "employees": {e["employee_id"]: e for e in load("employees.json", "employees")},
        "pto": {p["employee_id"]: p for p in load("pto_balances.json", "balances")},
        "benefits": {b["employee_id"]: b for b in load("benefits.json", "benefits")},
        "tickets": load("tickets.json", "tickets"),
    }


def reset_caches() -> None:
    _index.cache_clear()
    _data.cache_clear()


def _err(code: str, message: str, **extra) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, **extra}}


def _employee(employee_id: str) -> tuple[dict | None, dict | None]:
    eid = (employee_id or "").strip().upper()
    emp = _data()["employees"].get(eid)
    if emp is None:
        return None, _err("EMPLOYEE_NOT_FOUND", f"No employee with id '{employee_id}'.", hint="Employee ids look like E1001 (synthetic data: E1001-E1015).")
    return emp, None


def _date(s: str | None) -> dt.date | None:
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def _ref(emp_date: str | None = None) -> dt.date:
    return _date(emp_date) or settings.today()


def tenure(emp: dict, on: dt.date | None = None) -> dict:
    on = on or settings.today()
    start = dt.date.fromisoformat(emp["start_date"])
    days = (on - start).days
    intro_end = start + dt.timedelta(days=90)
    return {"tenure_days": days, "tenure_years": round(days / 365.25, 2), "intro_period_ends": intro_end.isoformat(), "in_intro_period": on < intro_end}


def annual_pto_entitlement(emp: dict, on: dt.date | None = None) -> float:
    """POL-001 §3: 15 / 20 / 25 days by service tier; part-time prorated by weekly hours / 40; contractors 0."""
    if emp["employment_type"] == "contractor":
        return 0.0
    years = tenure(emp, on)["tenure_years"]
    base = 15.0 if years < 2 else 20.0 if years < 5 else 25.0
    return round(base * (emp["weekly_hours"] / 40.0 if emp["employment_type"] == "part_time" else 1.0), 2)


def business_days_between(a: dt.date, b: dt.date) -> int:
    """Business days in [a, b) - the notice convention used by the compliance checker."""
    return int(np.busday_count(a.isoformat(), b.isoformat()))


def add_business_days(start: dt.date, n: int) -> list[dt.date]:
    """The n working days beginning on `start` (rolled forward if start is a weekend)."""
    first = np.busday_offset(start.isoformat(), 0, roll="forward")
    return [dt.date.fromisoformat(str(np.busday_offset(first, i))) for i in range(max(1, int(np.ceil(n))))]


def quarter_end_window(d: dt.date) -> set[dt.date]:
    """Last 5 business days of the calendar quarter that contains d (POL-001 §6 Finance blackout)."""
    if d.month not in (3, 6, 9, 12):
        return set()
    nxt = dt.date(d.year + (d.month == 12), (d.month % 12) + 1, 1)
    last = dt.date.fromisoformat(str(np.busday_offset(nxt.isoformat(), -1, roll="backward")))
    return {dt.date.fromisoformat(str(np.busday_offset(last.isoformat(), -i))) for i in range(5)}


# ----------------------------------------------------------------------------- RAG tools
def search_policy_documents(query: str, top_k: int = 5, doc_id: str | None = None) -> dict:
    if not query or not query.strip():
        return _err("EMPTY_QUERY", "Provide a non-empty query.")
    top_k = max(1, min(int(top_k), 10))
    res = _index().search(query, top_k=top_k, doc_id=doc_id.upper() if doc_id else None)
    return {"ok": True, **res, "index": {"documents": len(_index().documents()), "chunks": len(_index().chunks)}}


def get_policy_section(doc_id: str, section: str) -> dict:
    sec = _index().get_section(doc_id, section)
    if sec is None:
        avail = _index().sections_of(doc_id.strip().upper())
        if not avail:
            return _err("DOCUMENT_NOT_FOUND", f"Unknown policy document '{doc_id}'.", available=[d["doc_id"] for d in _index().documents()])
        return _err("SECTION_NOT_FOUND", f"Section '{section}' not found in {doc_id}.", available_sections=avail)
    return {"ok": True, **sec}


# ----------------------------------------------------------------------------- structured-data tools
def lookup_employee_profile(employee_id: str) -> dict:
    emp, err = _employee(employee_id)
    if err:
        return err
    mgr = _data()["employees"].get(emp["manager_id"]) if emp.get("manager_id") else None
    prof = {k: emp[k] for k in ("employee_id", "name", "email", "role", "department", "office", "country", "state_or_region",
                                "employment_type", "weekly_hours", "start_date", "work_arrangement", "data_access_level")}
    return {"ok": True, **prof, **tenure(emp),
            "manager": ({"employee_id": mgr["employee_id"], "name": mgr["name"], "role": mgr["role"], "email": mgr["email"]} if mgr else None),
            "synthetic": True}


def check_pto_balance(employee_id: str, days_requested: float | None = None) -> dict:
    emp, err = _employee(employee_id)
    if err:
        return err
    rec = _data()["pto"].get(emp["employee_id"])
    if rec is None or not rec["pto_eligible"]:
        return {"ok": True, "employee_id": emp["employee_id"], "pto_eligible": False,
                "reason": f"{emp['employment_type'].replace('_', ' ').title()} workers do not accrue PTO (POL-001 §2).",
                "policy": {"doc_id": "POL-001", "section": "2"}}
    available = round(rec["carryover_days"] + rec["accrued_ytd_days"] - rec["used_ytd_days"] - rec["pending_days"], 2)
    out = {"ok": True, "employee_id": emp["employee_id"], "pto_eligible": True, "as_of": rec["as_of"],
           "annual_entitlement_days": annual_pto_entitlement(emp), "carryover_days": rec["carryover_days"],
           "accrued_ytd_days": rec["accrued_ytd_days"], "used_ytd_days": rec["used_ytd_days"], "pending_days": rec["pending_days"],
           "available_days": available, "sick_days_remaining": rec["sick_days_remaining"],
           "floating_holidays_remaining": rec["floating_holidays_remaining"]}
    if days_requested is not None:
        d = float(days_requested)
        out.update(days_requested=d, sufficient_balance=available >= d, balance_after_request=round(available - d, 2))
    return out


def lookup_benefits_status(employee_id: str) -> dict:
    emp, err = _employee(employee_id)
    if err:
        return err
    rec = _data()["benefits"].get(emp["employee_id"])
    etype, hrs, country = emp["employment_type"], emp["weekly_hours"], emp["country"]
    if country != "US":
        elig = {"region": country, "summary": "Local (non-US) benefits apply; US medical/HSA/401(k)/wellness plans are not available (POL-006 §9)."}
    elif etype == "contractor" or hrs < 20:
        elig = {"region": "US", "summary": "Not eligible for Northwind benefits (POL-006 §2)."}
    elif etype == "part_time":
        elig = {"region": "US", "summary": "Part-time (>=20 h/week): eligible for dental, vision and 401(k) without match; not medical/wellness/life (POL-006 §2).",
                "medical": False, "dental": True, "vision": True, "k401": True, "k401_match": False, "wellness_stipend": False}
    else:
        elig = {"region": "US", "summary": "Full-time: eligible for all benefits from the 1st of the month after the start date (POL-006 §2).",
                "medical": True, "dental": True, "vision": True, "k401": True, "k401_match": True, "wellness_stipend": True}
    return {"ok": True, "employee_id": emp["employee_id"], "name": emp["name"], "employment_type": etype, "weekly_hours": hrs,
            "eligibility": elig, "elections": rec, "synthetic": True,
            "policy": {"doc_id": "POL-006", "section": "2"}}


# ----------------------------------------------------------------------------- mock actions
CATEGORIES = {"pto", "remote_work", "expense", "benefits", "equipment", "payroll", "employee_relations", "leave", "other"}


def create_mock_hr_ticket(employee_id: str, category: str, summary: str, details: str = "", priority: str = "normal", confirmed: bool = False) -> dict:
    """MOCK action. Without confirmed=True nothing is written - only a preview is returned."""
    emp, err = _employee(employee_id)
    if err:
        return err
    if category not in CATEGORIES:
        return _err("INVALID_CATEGORY", f"category must be one of {sorted(CATEGORIES)}")
    if priority not in {"low", "normal", "high"}:
        return _err("INVALID_PRIORITY", "priority must be low, normal or high")
    preview = {"employee_id": emp["employee_id"], "employee_name": emp["name"], "category": category, "summary": summary[:200],
               "details": details[:1500], "priority": priority}
    if not confirmed:
        return {"ok": True, "created": False, "status": "pending_confirmation", "preview": preview,
                "message": "No ticket was created. Re-call with confirmed=true only after the user explicitly approves."}
    path = settings.RUNTIME_DIR / "tickets_created.json"
    with _lock:
        settings.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        existing = json.loads(path.read_text()) if path.exists() else []
        ticket = {"ticket_id": f"HR-MOCK-{len(existing) + 1:04d}", **preview, "status": "open", "mock": True,
                  "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        existing.append(ticket)
        path.write_text(json.dumps(existing, indent=2))
    return {"ok": True, "created": True, "status": "created", "ticket": ticket,
            "message": "MOCK ticket created (no real HR system was contacted)."}


def draft_hr_email(employee_id: str, recipient: str, purpose: str, details: list[str] | None = None) -> dict:
    """Drafts text only - nothing is ever sent."""
    emp, err = _employee(employee_id)
    if err:
        return err
    if recipient not in {"manager", "hr", "it"}:
        return _err("INVALID_RECIPIENT", "recipient must be manager, hr or it")
    mgr = _data()["employees"].get(emp.get("manager_id") or "")
    to_name, to_email = {"manager": (mgr["name"], mgr["email"]) if mgr else ("your manager", ""),
                         "hr": ("People Operations", "people@northwind.example"), "it": ("IT Service Desk", "it-help@northwind.example")}[recipient][0:2] \
        if recipient != "manager" else ((mgr["name"], mgr["email"]) if mgr else ("Manager", ""))
    subjects = {"pto_request": "PTO request", "remote_work_request": "Request to work from another location", "expense_question": "Expense reimbursement question",
                "general": "Question from " + emp["name"]}
    openers = {"pto_request": "I would like to request time off. Here are the details:",
               "remote_work_request": "I would like to ask for approval to work temporarily from another location. Here are the details:",
               "expense_question": "I have a question about an expense. Here are the details:",
               "general": "I am writing about the following:"}
    if purpose not in subjects:
        purpose = "general"
    bullets = "\n".join(f"- {d}" for d in (details or []))
    body = (f"Hi {to_name.split()[0]},\n\n{openers[purpose]}\n\n{bullets}\n\n"
            f"Please let me know if you need anything else from me, and thank you for considering this.\n\nBest regards,\n{emp['name']}\n{emp['role']}")
    return {"ok": True, "sent": False, "to": {"name": to_name, "email": to_email}, "from": {"name": emp["name"], "email": emp["email"]},
            "subject": f"{subjects[purpose]} - {emp['name']}", "body": body,
            "note": "DRAFT ONLY. Nothing has been sent; review and send it yourself."}


# ----------------------------------------------------------------------------- compliance checker
def _chk(rule: str, status: str, detail: str, doc: str, section: str) -> dict:
    return {"rule": rule, "status": status, "detail": detail, "policy": {"doc_id": doc, "section": section}}


def _overall(checks: list[dict]) -> str:
    st = {c["status"] for c in checks}
    return "not_compliant" if "fail" in st else "needs_approval" if "needs_approval" in st else "compliant"


SANCTIONED = {"cuba", "iran", "north korea", "syria", "russia", "belarus", "crimea"}
APPROVED_COUNTRIES = {"united states", "canada", "united kingdom", "ireland", "germany", "france", "netherlands", "spain", "portugal",
                      "australia", "singapore", "pakistan"}
HIGH_COST_CITIES = {"new york", "san francisco", "london", "zurich", "tokyo"}


def _approver(total: float) -> str:
    return "Direct manager" if total <= 500 else "Department Director" if total <= 2500 else "Department VP (plus Finance review)"


def _pto_checks(emp: dict, start: dt.date | None, days: float | None) -> tuple[list[dict], list[str], list[str]]:
    today = settings.today()
    checks, approvals, notes = [], ["Direct manager (approval is always required)"], []
    if emp["employment_type"] == "contractor":
        return [_chk("eligibility", "fail", "Contractors are not eligible for PTO.", "POL-001", "2")], [], notes
    if days is None:
        return [_chk("request_details", "info", "Number of days not provided; cannot evaluate notice or balance.", "POL-001", "5")], approvals, notes
    on = start or today
    t = tenure(emp, on)
    if t["in_intro_period"]:
        checks.append(_chk("introductory_period", "needs_approval", f"Still in the 90-day introductory period until {t['intro_period_ends']}; PTO needs written People team approval.", "POL-001", "2"))
        approvals.append("People team (written approval during introductory period)")
    else:
        checks.append(_chk("introductory_period", "pass", "Introductory period completed.", "POL-001", "2"))
    required = 3 if days <= 2 else 10 if days <= 5 else 20
    if start:
        notice = business_days_between(today, start)
        if notice >= required:
            checks.append(_chk("notice_period", "pass", f"{notice} business days of notice given; {required} required for a {days:g}-day request.", "POL-001", "5"))
        else:
            checks.append(_chk("notice_period", "needs_approval", f"Only {notice} business days of notice; {required} required for a {days:g}-day request. This is a short-notice request that the manager may approve with a documented reason.", "POL-001", "7"))
            approvals.append("Manager exception for short notice (documented business reason)")
    else:
        checks.append(_chk("notice_period", "info", f"Start date not provided; a {days:g}-day request needs at least {required} business days of notice.", "POL-001", "5"))
    rec = _data()["pto"].get(emp["employee_id"])
    if rec:
        avail = rec["carryover_days"] + rec["accrued_ytd_days"] - rec["used_ytd_days"] - rec["pending_days"]
        if avail >= days:
            checks.append(_chk("balance", "pass", f"Available balance {avail:g} days covers the {days:g}-day request ({avail - days:g} left).", "POL-001", "3"))
        else:
            short = days - avail
            if short <= 2 and t["tenure_years"] >= 1 and not t["in_intro_period"]:
                checks.append(_chk("balance", "needs_approval", f"Available balance {avail:g} days is {short:g} short; an advance of up to 2 unearned days needs People team approval.", "POL-001", "7"))
                approvals.append("People team (advance of unearned PTO)")
            else:
                checks.append(_chk("balance", "fail", f"Available balance {avail:g} days is not enough for {days:g} days; negative balances are not allowed.", "POL-001", "7"))
    if days >= 3:
        notes.append("Share a short coverage plan with your manager (requests of 3+ days, POL-001 §5).")
    if emp["department"] == "Finance" and start:
        overlap = [d for d in add_business_days(start, int(np.ceil(days))) if d in quarter_end_window(d)]
        if len(overlap) > 1:
            checks.append(_chk("finance_quarter_end_blackout", "needs_approval", f"{len(overlap)} of the requested days fall in the last 5 business days of a quarter; more than 1 day needs Finance Director approval.", "POL-001", "6"))
            approvals.append("Finance Director (quarter-end blackout)")
    return checks, approvals, notes


def _remote_checks(emp: dict, start: dt.date | None, bdays: int | None, country: str | None, state: str | None) -> tuple[list[dict], list[str], list[str]]:
    today = settings.today()
    checks, approvals, notes = [], ["Direct manager"], ["Assumes no other temporary remote-work days have been used this calendar year."]
    if emp["employment_type"] == "contractor":
        return [_chk("eligibility", "fail", "Contractors follow their service agreement; the temporary remote-work policy is for employees.", "POL-003", "3")], [], notes
    on = start or today
    t = tenure(emp, on)
    if t["in_intro_period"]:
        checks.append(_chk("introductory_period", "fail", f"Employees in the 90-day introductory period (until {t['intro_period_ends']}) are not eligible for temporary work from another state or country.", "POL-003", "3"))
    else:
        checks.append(_chk("introductory_period", "pass", "Introductory period completed.", "POL-003", "3"))
    home = {"US": "united states", "PK": "pakistan", "GB": "united kingdom"}[emp["country"]]
    dest = (country or "").strip().lower() or None
    if dest in {"usa", "us", "u.s."}:
        dest = "united states"
    if dest in {"uk", "u.k.", "england", "britain", "great britain"}:
        dest = "united kingdom"
    international = bool(dest and dest != home)
    if not dest and state:
        international = False
    if not dest and not state:
        checks.append(_chk("destination", "info", "Destination not provided; destination-specific checks (approved countries, sanctions, tax) were not run.", "POL-003", "5"))
    if dest and dest in SANCTIONED:
        checks.append(_chk("sanctioned_destination", "fail", f"{country} is subject to comprehensive sanctions; requests are always denied.", "POL-003", "5"))
    limit_section = "5" if (international or (not dest and not state)) else "4"
    if bdays is not None:
        if bdays <= 20:
            checks.append(_chk("duration_limit", "pass", f"{bdays} business days is within the 20-business-day annual limit.", "POL-003", limit_section))
        else:
            checks.append(_chk("duration_limit", "fail", f"{bdays} business days exceeds the 20-business-day annual limit; only an exception approved by the department VP, the Chief People Officer and Tax/Legal can allow it.", "POL-003", limit_section))
            approvals += ["Department VP (exception)", "Chief People Officer (exception)", "Tax and Legal (exception)"]
    else:
        checks.append(_chk("duration_limit", "info", "Duration not provided; the limit is 20 business days per calendar year.", "POL-003", limit_section))
    if international or (not dest and not state):
        need_days = 30
        if start:
            lead = (start - today).days
            checks.append(_chk("notice_period", "pass" if lead >= need_days else "needs_approval",
                               f"{lead} calendar days of notice; international requests need at least {need_days}." + ("" if lead >= need_days else " Notice requirement is not met."), "POL-003", "5"))
        else:
            checks.append(_chk("notice_period", "info", "Start date not provided; international requests need at least 30 calendar days of notice.", "POL-003", "5"))
        approvals += ["Department VP", "People team", "Tax and Legal review (Security and Tax intake form)"]
        if emp["data_access_level"] in {"Confidential", "Restricted"}:
            if dest:
                if dest in APPROVED_COUNTRIES:
                    checks.append(_chk("approved_country", "pass", f"{country} is on the approved list for {emp['data_access_level']} data access.", "POL-004", "4"))
                elif dest not in SANCTIONED:
                    checks.append(_chk("approved_country", "fail", f"{country} is not an approved country for {emp['data_access_level']} data access; sign-ins would be blocked unless the CISO approves an exception in writing.", "POL-004", "4"))
                    approvals.append("CISO (written exception for a non-approved country)")
            checks.append(_chk("security_review", "needs_approval", f"{emp['data_access_level']} data access requires a security review before travel.", "POL-004", "5"))
            approvals.append("Security review (CISO team)")
        else:
            checks.append(_chk("data_access", "pass", "Standard data access: no approved-country restriction (sanctioned countries still excluded).", "POL-004", "4"))
        notes.append("You are responsible for having the legal right to be present and work in the destination (no visa sponsorship).")
    else:
        if start:
            lead = business_days_between(today, start)
            checks.append(_chk("notice_period", "pass" if lead >= 10 else "needs_approval", f"{lead} business days of notice; domestic requests need at least 10.", "POL-003", "4"))
        checks.append(_chk("tax_notification", "needs_approval", "Tell People so payroll tax withholding for the other state can be reviewed.", "POL-003", "4"))
        approvals.append("People team (payroll tax review)")
    return checks, approvals, notes


def _expense_checks(emp: dict, item: str, amount: float | None, nights: int | None, city: str | None, flight_hours: float | None, cabin: str | None) -> tuple[list[dict], list[str], list[str], float | None]:
    today = settings.today()
    it = (item or "other").lower()
    checks, approvals, notes, reimb = [], [], [], amount
    if emp["employment_type"] == "contractor":
        return [_chk("eligibility", "fail", "Contractors are not covered by the expense policy unless their agreement says so.", "POL-012", "1")], [], notes, 0.0
    if it in {"laptop", "computer", "phone", "tablet", "monitor", "software"}:
        checks.append(_chk("equipment_not_reimbursable", "fail", "Laptops, computers, phones, monitors and software are provided by IT and cannot be reimbursed; request them through an IT ticket.", "POL-005", "7"))
        notes.append("Submit an equipment request to the IT Service Desk (POL-010 §4).")
        return checks, approvals, notes, 0.0
    if it in {"chair", "desk", "home_office", "monitor_stand", "keyboard", "mouse", "lighting"}:
        t = tenure(emp, today)
        arr = emp["work_arrangement"]
        if arr == "office":
            checks.append(_chk("home_office_eligibility", "fail", "Office-based employees are not eligible for the home office stipend.", "POL-005", "6"))
            return checks, approvals, notes, 0.0
        if t["in_intro_period"]:
            checks.append(_chk("introductory_period", "fail", f"The home office stipend requires completing the 90-day introductory period (ends {t['intro_period_ends']}).", "POL-005", "6"))
            return checks, approvals, notes, 0.0
        limit = 400.0 if arr == "remote" else 200.0
        checks.append(_chk("home_office_eligibility", "pass", f"{arr.title()} employee past the introductory period: one-time stipend of ${limit:g}; ergonomic chairs and desks are covered.", "POL-005", "6"))
        if amount is not None and amount > limit:
            checks.append(_chk("stipend_limit", "needs_approval", f"Amount ${amount:g} exceeds the ${limit:g} stipend; only ${limit:g} is reimbursable, the rest is your own cost.", "POL-005", "6"))
            reimb = limit
        notes.append("The stipend is one-time; submit an itemized receipt within 30 days of purchase.")
    elif it in {"hotel", "lodging"}:
        cap = 325.0 if (city or "").lower() in HIGH_COST_CITIES else 250.0
        if amount is not None and nights:
            per = amount / nights
            checks.append(_chk("lodging_cap", "pass" if per <= cap else "needs_approval", f"${per:.0f}/night vs cap ${cap:g}/night." + ("" if per <= cap else " Only the capped amount is reimbursable."), "POL-005", "5"))
            if per > cap:
                reimb = cap * nights
        else:
            checks.append(_chk("lodging_cap", "info", f"Cap is ${cap:g} per night (${325 if cap == 325 else 250} in {'high-cost cities' if cap == 325 else 'other locations'}).", "POL-005", "5"))
    elif it in {"meal", "meals"}:
        checks.append(_chk("meal_per_diem", "pass" if (amount is None or amount <= 75) else "needs_approval", "Meals are reimbursable only during approved business travel, up to a $75 per-day per diem; alcohol is not reimbursable.", "POL-005", "4"))
        if amount is not None and amount > 75:
            reimb = 75.0
    elif it in {"airfare", "flight"}:
        long = (flight_hours or 0) > 6
        cls = (cabin or "economy").lower()
        if cls in {"business", "first"}:
            checks.append(_chk("airfare_class", "fail", "Business and first class are not reimbursable.", "POL-005", "5"))
            reimb = None
        elif cls == "premium economy" and not long:
            checks.append(_chk("airfare_class", "fail", "Premium economy is allowed only for flights longer than 6 hours.", "POL-005", "5"))
        else:
            checks.append(_chk("airfare_class", "pass", "Economy (or premium economy on flights over 6 hours) is reimbursable.", "POL-005", "5"))
        approvals.append("Pre-approval before booking; international travel also needs Director approval (POL-011 §2)")
    elif it in {"client_entertainment"}:
        checks.append(_chk("client_entertainment", "needs_approval", "Client entertainment must be pre-approved by a Director and is limited to $100 per person; alcohol limited to two drinks per person.", "POL-005", "4"))
    else:
        checks.append(_chk("general", "info", "No item-specific rule matched; general submission rules apply.", "POL-005", "2"))
    if amount is not None:
        approvals.append(_approver(amount) + " approval for the report total")
        checks.append(_chk("receipt", "info", "Itemized receipt required (over $25)." if amount > 25 else "Receipt not required at $25 or less.", "POL-005", "2"))
    notes.append("Submit within 30 days of the expense date.")
    return checks, approvals, notes, reimb


def check_policy_compliance(employee_id: str, scenario: str, start_date: str | None = None, days: float | None = None,
                            destination_country: str | None = None, destination_state: str | None = None, business_days: int | None = None,
                            item: str | None = None, amount: float | None = None, nights: int | None = None, city: str | None = None,
                            flight_hours: float | None = None, cabin_class: str | None = None) -> dict:
    """Deterministic rule engine that encodes the written policies (every check cites doc + section)."""
    emp, err = _employee(employee_id)
    if err:
        return err
    start = _date(start_date)
    if start_date and start is None:
        return _err("INVALID_DATE", f"start_date must be ISO YYYY-MM-DD, got '{start_date}'.")
    extra: dict[str, Any] = {}
    if scenario == "pto_request":
        checks, approvals, notes = _pto_checks(emp, start, days)
    elif scenario == "remote_work":
        checks, approvals, notes = _remote_checks(emp, start, business_days, destination_country, destination_state)
    elif scenario == "expense":
        checks, approvals, notes, reimb = _expense_checks(emp, item or "other", amount, nights, city, flight_hours, cabin_class)
        extra["reimbursable_amount"] = reimb
    else:
        return _err("UNKNOWN_SCENARIO", "scenario must be one of: pto_request, remote_work, expense")
    overall = _overall(checks)
    if any("(exception)" in a for a in approvals):  # exception chain replaces the standard VP / Tax approvals
        approvals = [a for a in approvals if a not in ("Department VP", "Tax and Legal review (Security and Tax intake form)")]
    seen, uniq = set(), []
    for a in approvals:
        if a not in seen:
            seen.add(a)
            uniq.append(a)
    return {"ok": True, "employee_id": emp["employee_id"], "scenario": scenario, "evaluated_on": settings.today().isoformat(),
            "overall": overall, "checks": checks, "approvals_required": uniq, "notes": notes, **extra}
