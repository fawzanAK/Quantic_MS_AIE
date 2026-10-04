"""Deterministic request understanding: slot extraction + intent classification (pure functions, unit-tested).

An optional LLM can override a *low-confidence* classification (see agent.py); this module is the always-available baseline.
"""
from __future__ import annotations

import datetime as dt
import re

import numpy as np

WORD_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
            "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20}
_NUM = r"(\d+(?:\.\d+)?|" + "|".join(WORD_NUM) + r")"
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
WEEKDAYS = {d: i for i, d in enumerate(["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"])}

COUNTRIES = {
    "united states": "United States", "usa": "United States", "canada": "Canada", "mexico": "Mexico", "brazil": "Brazil", "argentina": "Argentina",
    "united kingdom": "United Kingdom", "uk": "United Kingdom", "ireland": "Ireland", "france": "France", "germany": "Germany", "spain": "Spain",
    "portugal": "Portugal", "italy": "Italy", "netherlands": "Netherlands", "switzerland": "Switzerland", "sweden": "Sweden", "norway": "Norway",
    "poland": "Poland", "turkey": "Turkey", "greece": "Greece", "egypt": "Egypt", "south africa": "South Africa", "kenya": "Kenya", "nigeria": "Nigeria",
    "india": "India", "pakistan": "Pakistan", "bangladesh": "Bangladesh", "sri lanka": "Sri Lanka", "thailand": "Thailand", "vietnam": "Vietnam",
    "japan": "Japan", "south korea": "South Korea", "china": "China", "singapore": "Singapore", "malaysia": "Malaysia", "indonesia": "Indonesia",
    "philippines": "Philippines", "australia": "Australia", "new zealand": "New Zealand", "uae": "United Arab Emirates", "dubai": "United Arab Emirates",
    "saudi arabia": "Saudi Arabia", "qatar": "Qatar", "russia": "Russia", "belarus": "Belarus", "iran": "Iran", "cuba": "Cuba", "north korea": "North Korea",
    "syria": "Syria", "ukraine": "Ukraine",
}
US_STATES = ["alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
             "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan", "minnesota", "mississippi",
             "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey", "new mexico", "new york state", "north carolina", "north dakota", "ohio",
             "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina", "south dakota", "tennessee", "texas", "utah", "vermont", "virginia",
             "washington state", "west virginia", "wisconsin", "wyoming"]
HIGH_COST = ["new york", "san francisco", "london", "zurich", "tokyo"]


def _num(tok: str) -> float:
    return float(WORD_NUM[tok]) if tok in WORD_NUM else float(tok)


def _next_weekday(today: dt.date, wd: int, strictly_after: bool = True) -> dt.date:
    delta = (wd - today.weekday()) % 7
    if delta == 0 and strictly_after:
        delta = 7
    return today + dt.timedelta(days=delta)


def parse_date(text: str, today: dt.date) -> tuple[dt.date | None, str | None]:
    low = text.lower()
    m = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", low)
    if m:
        try:
            return dt.date(int(m[1]), int(m[2]), int(m[3])), m[0]
        except ValueError:
            pass
    m = re.search(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(20\d{2}))?\b", low)
    if not m:
        m2 = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b(?:,?\s*(20\d{2}))?", low)
        if m2:
            m = type("M", (), {"__getitem__": lambda s, i: (m2[0], m2[2], m2[1], m2[3])[i]})()
    if m:
        try:
            month, day = MONTHS[m[1]], int(m[2])
            year = int(m[3]) if m[3] else today.year
            d = dt.date(year, month, day)
            if not m[3] and d < today:
                d = dt.date(year + 1, month, day)
            return d, m[0]
        except (ValueError, KeyError):
            pass
    if "tomorrow" in low:
        return today + dt.timedelta(days=1), "tomorrow"
    if re.search(r"\bnext week\b", low):
        return today + dt.timedelta(days=7 - today.weekday()), "next week"
    if re.search(r"\bnext month\b", low):
        first = dt.date(today.year + (today.month == 12), (today.month % 12) + 1, 1)
        return first + dt.timedelta(days=(7 - first.weekday()) % 7 if first.weekday() > 4 else 0), "next month"
    m = re.search(r"\b(?:next|this|on)\s+(monday|tuesday|wednesday|thursday|friday)\b", low)
    if m:
        return _next_weekday(today, WEEKDAYS[m[1]]), m[0]
    return None, None


def extract_slots(message: str, today: dt.date) -> dict:
    low = message.lower()
    s: dict = {}
    m = re.search(r"\bE\d{4}\b", message, re.I)
    if m:
        s["employee_id"] = m[0].upper()
    # duration
    m = re.search(_NUM + r"\s*(?:-|\s)?\s*(?:business\s+|working\s+)?(weeks?)\b", low)
    if m and not re.search(r"\bnext\s+" + re.escape(m[1]) + r"\s*weeks?\b", low):
        s["business_days"] = int(_num(m[1]) * 5)
        s["days"] = _num(m[1]) * 5
        s["duration_text"] = m[0]
    m = re.search(_NUM + r"\s*(?:business\s+|working\s+)?days?\b", low)
    if m and "days" not in s:
        s["days"] = _num(m[1])
        s["business_days"] = int(_num(m[1]))
        s["duration_text"] = m[0]
    m = re.search(r"\b(\d+|" + "|".join(WORD_NUM) + r")\s+months?\b", low)
    if m and "days" not in s:
        s["business_days"] = int(_num(m[1]) * 21)
        s["days"] = float(s["business_days"])
        s["duration_text"] = m[0]
    if re.search(r"\bhalf(?:\s+a)?\s+day\b", low):
        s["days"], s["business_days"] = 0.5, 1
    d, txt = parse_date(message, today)
    if d:
        s["start_date"], s["date_text"] = d.isoformat(), txt
    # explicit range such as "Dec 22 to Dec 24" -> inclusive working days
    mon = "|".join(sorted(MONTHS, key=len, reverse=True))
    rng = re.search(r"\b(" + mon + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?\s*(?:to|through|until|-|–)\s*(?:(" + mon + r")\.?\s+)?(\d{1,2})(?:st|nd|rd|th)?\b", low)
    if rng:
        try:
            m1, d1 = MONTHS[rng[1]], int(rng[2])
            m2, d2 = (MONTHS[rng[3]] if rng[3] else m1), int(rng[4])
            a = dt.date(today.year, m1, d1)
            if a < today:
                a = dt.date(today.year + 1, m1, d1)
            b = dt.date(a.year + (m2 < m1), m2, d2)
            n = int(np.busday_count(a.isoformat(), (b + dt.timedelta(days=1)).isoformat()))
            if n > 0:
                s.update(start_date=a.isoformat(), end_date=b.isoformat(), days=float(n), business_days=n, date_text=rng[0], duration_text=f"{n} working days")
        except (ValueError, KeyError):
            pass
    # destination
    for name in sorted(COUNTRIES, key=len, reverse=True):
        if re.search(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", low):
            s["destination_country"] = COUNTRIES[name]
            break
    for st in US_STATES:
        if re.search(r"(?<![a-z])" + re.escape(st) + r"(?![a-z])", low):
            s["destination_state"] = st.replace(" state", "").title()
            break
    if "destination_country" not in s and "destination_state" not in s:
        if re.search(r"another country|abroad|overseas|international|outside the (?:us|country)|foreign", low):
            s["destination_hint"] = "international"
        elif re.search(r"another state|different state|out of state", low):
            s["destination_hint"] = "domestic"
    # expense
    items = [(r"laptop|macbook|computer|notebook pc", "laptop"), (r"\bphone|smartphone|tablet|ipad", "phone"), (r"monitor stand", "monitor_stand"),
             (r"\bmonitor|screen", "monitor"), (r"\bchair", "chair"), (r"standing desk|\bdesk", "desk"), (r"home office", "home_office"),
             (r"hotel|lodging|accommodation", "hotel"), (r"client (?:dinner|lunch|entertain)|entertain", "client_entertainment"),
             (r"\bmeals?\b|dinner|lunch|breakfast|per diem", "meal"), (r"flight|airfare|plane ticket|airline", "airfare")]
    for pat, name in items:
        if re.search(pat, low):
            s["item"] = name
            break
    m = re.search(r"\$\s?(\d[\d,]*(?:\.\d+)?)|(\d[\d,]*(?:\.\d+)?)\s*(?:dollars|usd)\b", low)
    if m:
        s["amount"] = float((m[1] or m[2]).replace(",", ""))
    m = re.search(r"(\d+)\s*nights?\b", low)
    if m:
        s["nights"] = int(m[1])
    for c in HIGH_COST:
        if c in low:
            s["city"] = c
    m = re.search(r"(\d+(?:\.\d+)?)[- ]hours?\b", low)
    if m:
        s["flight_hours"] = float(m[1])
    if re.search(r"business class|first class", low):
        s["cabin_class"] = "business"
    elif "premium economy" in low:
        s["cabin_class"] = "premium economy"
    return s


# ----------------------------------------------------------------------------- classification
_SENSITIVE = re.compile(r"harass|discriminat|retaliat|bully|bullied|hostile|assault|unsafe|threaten|abus(?:e|ive)|racis|sexis|toxic|intimidat|"
                        r"inappropriate (?:comment|touch|behavio)|treated unfairly|being targeted|whistle", re.I)
_PERSONAL = re.compile(r"\b(?:can i|may i|do i|am i|will i|should i|could i|would i|my|i am|i'm|i need|i want|i'd like|i would like|i have|i got|i plan|i was|i've|me)\b", re.I)
_PTO = re.compile(r"\bpto\b|vacation|time off|days? off|paid time off|\btake\b.{0,40}\boff\b|take (?:\w+\s+){0,4}(?:days?|week)\b|(?:take|book|request|use)\s+(?:\w+\s+){0,3}leave\b", re.I)
_POLICY_WORDS = re.compile(r"carry|accru|expire|polic|\brules?\b|limit|maximum|how (?:do|does)|what (?:is|are|happens)|\bwho\b|when (?:do|does|is)|notice period|approval", re.I)
_BALANCE = re.compile(r"balance|how many|left|remaining|available|how much|accrued", re.I)
_REMOTE = re.compile(r"remote|work(?:ing)? from|\bwfh\b|abroad|overseas|another (?:state|country)|workation|telework|from home|work(?:ing)? in (?:a )?(?:different|another)", re.I)
_EXPENSE = re.compile(r"reimburs|expens|per diem|stipend|receipt|claim", re.I)
_BENEFITS = re.compile(r"benefit|401|medical|dental|vision|insurance|\bhsa\b|enroll|dependents?|coverage|wellness stipend|health plan", re.I)

TOPICS: dict[str, tuple[str, str]] = {
    "pto": (r"\bpto\b|vacation|time off|days? off|accru|carry[\s-]?over|paid time off", "PTO accrual carryover notice approval"),
    "holidays": (r"holiday|floating", "paid company holidays floating holidays"),
    "sick": (r"\bsick\b|illness", "sick leave days medical certificate"),
    "parental": (r"parental|maternity|paternity|new baby|newborn|adopt", "parental leave primary secondary caregiver"),
    "leave": (r"fmla|bereavement|jury|military|disability|medical leave|leave of absence", "leave of absence FMLA bereavement jury duty"),
    "remote": (r"remote|work(?:ing)? from|hybrid|abroad|workation|another (?:state|country)|core days", "remote work hybrid temporary work another location"),
    "security": (r"security|\bvpn\b|data classif|phishing|password|\bmfa\b|encrypt|approved countr|incident", "information security data classification approved countries VPN"),
    "expense": (r"expens|reimburs|per diem|receipt|stipend|approval limit", "expense reimbursement approval limits per diem home office stipend"),
    "travel": (r"travel|flight|airfare|hotel|visa\b|\btrip\b", "business travel booking airfare hotel visa"),
    "benefits": (r"benefit|401|medical|dental|vision|\bhsa\b|open enrollment|insurance|wellness", "benefits eligibility medical dental vision 401(k)"),
    "onboarding": (r"onboard|new hire|first day|introductory|probation|30-60-90", "onboarding checklist introductory period"),
    "equipment": (r"laptop|equipment|monitor|headset|refresh|lost|stolen|\bbyod\b|\bit\b ticket", "equipment laptop refresh requests lost stolen"),
    "conduct": (r"conduct|gift|conflict of interest|hotline|ethics|report (?:a|an|my)|outside (?:work|employment)", "code of conduct reporting concerns Employee Relations gifts"),
    "payroll": (r"payroll|paycheck|pay date|salary|bonus|overtime|direct deposit|pay schedule", "payroll pay schedule direct deposit overtime"),
    "performance": (r"performance|\bpip\b|promotion|warning|review cycle", "performance review cycle improvement plan"),
    "learning": (r"tuition|learning budget|training|conference|course|degree|\bmba\b", "learning budget tuition reimbursement conferences"),
    "wellbeing": (r"\beap\b|counsel|accommodat|injur|safety|wellbeing|ergonomic", "wellbeing EAP accommodations injury reporting"),
    "office": (r"\boffice\b|\bdesk\b|visitor|parking|badge|meeting room", "office desk booking visitors badge"),
    "employment": (r"contractor|part[\s-]?time|full[\s-]?time|exempt|notice period|resign|transfer|intern\b", "employment types contractor part-time exempt notice"),
}


def detect_topics(message: str) -> list[str]:
    return [k for k, (pat, _) in TOPICS.items() if re.search(pat, message, re.I)]


def classify(message: str, slots: dict) -> dict:
    """Return {intent, confidence, personal, topics, reasons}."""
    low = message.lower()
    personal = bool(_PERSONAL.search(message))
    topics = detect_topics(message)
    flags = {"pto": bool(_PTO.search(low)), "remote": bool(_REMOTE.search(low)), "expense": bool(_EXPENSE.search(low) or slots.get("item") in {"laptop", "chair", "desk", "home_office", "hotel", "airfare"} and "reimburs" in low),
             "benefits": bool(_BENEFITS.search(low))}
    reasons: list[str] = []

    def out(intent: str, conf: float):
        return {"intent": intent, "confidence": conf, "personal": personal, "topics": topics, "reasons": reasons}

    if _SENSITIVE.search(message):
        reasons.append("sensitive-workplace keywords")
        return out("hr_case", 0.9)
    if flags["pto"] and personal:
        has_amount = "days" in slots or "start_date" in slots
        if re.search(r"balance|left|remaining|available|how many .*(?:do i|have)|how much", low) and not re.search(r"\bcan i\b|\bmay i\b|take|book|request", low):
            reasons.append("personal PTO balance question")
            return out("pto_balance", 0.85)
        if has_amount and re.search(r"\bcan i\b|\bmay i\b|take|book|request|use|need|want|would like|plan", low):
            reasons.append("personal PTO request with days/dates")
            return out("pto_request", 0.9)
        if _POLICY_WORDS.search(low):
            reasons.append("PTO policy question phrased in the first person")
            return out("policy_qa", 0.7)
        reasons.append("personal PTO wording without days or dates")
        return out("ambiguous", 0.7)
    if flags["remote"] and personal and not re.search(r"\bwhat(?:'s| is) the\b.*\bpolicy\b", low):
        has_detail = any(k in slots for k in ("business_days", "destination_country", "destination_state", "destination_hint", "start_date"))
        reasons.append("personal remote-work request" + ("" if has_detail else " without destination or duration"))
        return out("remote_work" if has_detail else "ambiguous", 0.85 if has_detail else 0.7)
    if (flags["expense"] or slots.get("item") in {"laptop", "chair", "desk", "home_office", "hotel", "airfare", "monitor", "meal"} and re.search(r"reimburs|expens|claim|cover", low)) and personal and slots.get("item"):
        reasons.append("personal expense/reimbursement question")
        return out("expense", 0.85)
    generic_subject = bool(re.search(r"\b(?:new hires?|employees?|staff|people|someone|contractors?)\b", low)) or len(topics) >= 3
    if flags["expense"] and not personal and not generic_subject and slots.get("item") in {"laptop", "chair", "desk", "home_office", "monitor"} and re.search(r"\b(?:can|could|is|are)\b", low):
        reasons.append("expense eligibility question (no personal marker)")
        return out("expense", 0.6)
    if flags["benefits"] and personal:
        reasons.append("personal benefits question")
        return out("benefits", 0.8)
    if topics or any(flags.values()):
        reasons.append("general policy question on: " + ", ".join(topics or [k for k, v in flags.items() if v]))
        return out("policy_qa", 0.75)
    if len(low.split()) <= 3 or (len(low.split()) <= 4 and personal):
        reasons.append("very short request with no recognisable HR topic")
        return out("ambiguous", 0.6)
    reasons.append("no HR topic detected")
    return out("out_of_scope", 0.5)
