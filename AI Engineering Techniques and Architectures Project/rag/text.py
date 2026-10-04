"""Text normalisation shared by indexing and querying (must be identical on both sides)."""
from __future__ import annotations

import re

STOPWORDS = frozenset(
    """a an the and or of to in on for with at by from is are was were be been being it its this that these
    those as if then than so such can could may might will would shall should do does did have has had i you we
    they he she me my our your their not no nor but about into over under up down out per via also any all each
    other more most what which who whom how when where why there here get many much long tell please today currently know give like want let offer offers provide provides""".split()
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_SUFFIXES = ("ations", "ation", "ments", "ment", "ities", "ity", "ables", "able", "ings", "ing", "ied", "ed", "es", "s", "ly")


def stem(tok: str) -> str:
    """Tiny deterministic suffix stripper (no external model/download needed)."""
    if len(tok) <= 3 or tok.isdigit():
        return tok
    if tok.endswith("ies") and len(tok) > 4:
        return tok[:-3] + "y"
    for suf in _SUFFIXES:
        if tok.endswith(suf) and len(tok) - len(suf) >= 3:
            tok = tok[: -len(suf)]
            break
    if tok.endswith("e") and len(tok) > 3:
        tok = tok[:-1]
    return tok


def tokens(text: str) -> list[str]:
    """Lowercased, stop-word-filtered, stemmed unigrams."""
    out = []
    for t in _TOKEN_RE.findall(text.lower()):
        if t in STOPWORDS or (len(t) == 1 and not t.isdigit()):
            continue
        out.append(stem(t))
    return out


def analyzer(text: str) -> list[str]:
    """Unigrams + bigrams, used by the TF-IDF vectoriser."""
    toks = tokens(text)
    return toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]


# Query rewriting: expand colloquial wording into the vocabulary the policies actually use.
_REWRITES = [
    (r"carry[\s-]?over|roll(?:ed)? over|expire", "carryover unused PTO days expire"),
    (r"\bvacation|time off|days? off|holiday leave\b", "PTO paid time off"),
    (r"\bwfh\b|work(?:ing)? from home", "remote work hybrid"),
    (r"\babroad\b|overseas|another country|international|foreign|outside the (?:us|country)", "international remote work country approved countries"),
    (r"\banother state|different state|out of state", "work from another state tax payroll same country"),
    (r"\breimburs\w*|expens\w*|claim\b", "expense reimbursement"),
    (r"\blaptop|computer|macbook\b", "laptop equipment IT"),
    (r"\bchair|desk|ergonomic|home office\b", "home office stipend ergonomic chair"),
    (r"\bmaternity|paternity|new baby|newborn|adoption\b", "parental leave primary secondary caregiver"),
    (r"\b401\s?\(?k\)?|retirement|pension\b", "401(k) retirement match"),
    (r"\bhealth insurance|medical plan|insurance\b", "medical plan benefits eligibility"),
    (r"\bharass\w*|bully\w*|discriminat\w*|retaliat\w*", "harassment discrimination report Employee Relations investigation"),
    (r"\bsick\b|\bill(?:ness)?\b", "sick leave sick days"),
    (r"\bfired|terminat\w*|resign\w*|quit\b", "termination resignation notice final pay"),
    (r"\bvpn|encrypt\w*|phishing|password\b", "security device VPN MFA incident"),
]


def rewrite_query(query: str) -> str:
    """Append domain vocabulary for colloquial phrases (keeps the original query intact)."""
    extra: list[str] = []
    low = query.lower()
    for pat, add in _REWRITES:
        if re.search(pat, low):
            extra.append(add)
    return (query + " " + " ".join(extra)).strip() if extra else query
