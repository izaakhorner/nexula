"""Pull support-team performance metrics from Creatio and aggregate them.

This module is the whole Creatio integration for the dashboard. It logs in to prod
Creatio with a session login (+ BPMCSRF header), reads Cases over OData, and rolls the
rows up into exactly three things:

  1. Tickets closed by IC  - closed cases attributed to each support agent.
  2. Survey scores         - the Case "Satisfaction level" field, per IC, scored as NPS.
  3. AI-agent adoption     - of CLOSED cases that had an AI draft, how many used the draft.
                             (Adoption is computed over closed tickets only, by request.)

Auth: prod Creatio session login + BPMCSRF header. Credentials are supplied by the UI at
runtime (held only in the server's memory) or from a local .env; nothing is hardcoded.
"""

from __future__ import annotations

import http.cookiejar
import json
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGE = 1000
NULL_GUID = "00000000-0000-0000-0000-000000000000"  # Creatio's empty-lookup sentinel

# Case navigation property for the survey field. In stock Creatio Service the "Satisfaction
# level" lookup is `SatisfactionLevel`; override via .env if your instance renamed it.
DEFAULT_SATISFACTION_FIELD = "SatisfactionLevel"

# Survey-score model (matches the existing spreadsheet's NPS methodology):
#   promoters  = Excellent + Good      detractors = Poor + Extremely poor
#   NPS        = (promoters - detractors) / responses * 100
# and a simple 1-5 CSAT scale for an average score.
SATISFACTION_SCALE = {
    "excellent": 5,
    "good": 4,
    "neutral": 3,
    "poor": 2,
    "extremely poor": 1,
}
PROMOTERS = {"excellent", "good"}
DETRACTORS = {"poor", "extremely poor"}

# The current customer-support roster (name -> level). Used to (a) tag each IC with a level
# and (b) restrict the default view to the support team. Matching tolerates minor Creatio
# spelling drift (see `_match_roster`). "Mostafa Essam" and "Mostafa Essa" are two people.
SUPPORT_ROSTER = {
    "Oliver Asuncion": "Level 1",
    "Anton Lopez": "Level 1",
    "Rahul Kumar": "Level 1",
    "Aditya Katyayan": "Level 1",
    "Abdul Hassan": "Level 1",
    "Marc Magno": "Level 1",
    "Jae Villalobos": "Level 1",
    "Hisham Abdelrashid": "Level 1",
    "Mostafa Essa": "Level 1",
    "Youssef Eissa": "Level 2",
    "Mostafa Essam": "Level 2",
    "Youssef Ibrahim": "Level 2",
}


# --------------------------------------------------------------------------- #
# Name matching (tolerant of Creatio spelling drift)                          #
# --------------------------------------------------------------------------- #
def _norm_name(s: str) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalpha())


def _lev(a: str, b: str) -> int:
    """Levenshtein edit distance (iterative, two-row)."""
    m, n = len(a), len(b)
    if not m:
        return n
    if not n:
        return m
    prev = list(range(n + 1))
    for i in range(1, m + 1):
        cur = [i] + [0] * n
        for j in range(1, n + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1]))
        prev = cur
    return prev[n]


_ROSTER_NORM = {_norm_name(name): (name, lvl) for name, lvl in SUPPORT_ROSTER.items()}


def _match_roster(name: str) -> tuple[str, str] | None:
    """Return (canonical_name, level) if `name` is (close to) someone on the roster, else None."""
    x = _norm_name(name)
    if not x:
        return None
    if x in _ROSTER_NORM:
        return _ROSTER_NORM[x]
    for norm, val in _ROSTER_NORM.items():
        if _lev(norm, x) <= 2:
            return val
    return None


# --------------------------------------------------------------------------- #
# Creatio connection                                                          #
# --------------------------------------------------------------------------- #
def load_env() -> dict[str, str]:
    """Read CREATIO_* from a local .env (owner convenience). The UI path passes creds directly."""
    env: dict[str, str] = {}
    envfile = HERE / ".env"
    if not envfile.exists():
        raise RuntimeError("Missing .env - copy .env.example to .env, or enter creds in the UI.")
    for line in envfile.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    for req in ("CREATIO_URL", "CREATIO_USER", "CREATIO_PASS"):
        if not env.get(req):
            raise RuntimeError(f"Missing {req} in .env")
    return env


def login(base: str, user: str, password: str):
    """Prod Creatio auth: POST AuthService.svc/Login, keep the cookie jar, grab BPMCSRF.

    Returns (opener, csrf). Every subsequent OData call must send the BPMCSRF header and the
    ForceUseSession header, and reuse this opener so the session cookie rides along.
    """
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    body = json.dumps({"UserName": user, "UserPassword": password}).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/ServiceModel/AuthService.svc/Login",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with opener.open(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("Code", 0) != 0:
        raise RuntimeError(f"Creatio login failed: {payload.get('Message') or payload}")
    csrf = next((c.value for c in jar if c.name == "BPMCSRF"), None)
    if not csrf:
        raise RuntimeError("Login succeeded but no BPMCSRF cookie returned.")
    return opener, csrf


def _get(base: str, opener, csrf: str, path_qs: str) -> dict:
    req = urllib.request.Request(
        f"{base}/0/odata/{path_qs}",
        headers={"Accept": "application/json", "BPMCSRF": csrf, "ForceUseSession": "true"},
    )
    with opener.open(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _date_filter(date_from: str | None, date_to: str | None) -> str:
    """OData clause scoping Case.CreatedOn to [from 00:00, to 23:59:59] UTC. Either bound optional."""
    parts: list[str] = []
    if date_from:
        parts.append(f"CreatedOn ge {date_from}T00:00:00Z")
    if date_to:
        parts.append(f"CreatedOn le {date_to}T23:59:59Z")
    return (" and " + " and ".join(parts)) if parts else ""


def _page_cases(base: str, opener, csrf: str, select: str, expand: str, filt: str) -> list[dict]:
    """Page through /0/odata/Case with the given $select/$expand/$filter."""
    rows: list[dict] = []
    skip = 0
    while True:
        qs = urllib.parse.urlencode(
            {"$select": select, "$expand": expand, "$filter": filt, "$top": PAGE, "$skip": skip}
        )
        batch = _get(base, opener, csrf, f"Case?{qs}").get("value", [])
        rows.extend(batch)
        if len(batch) < PAGE:
            break
        skip += PAGE
    return rows


def _fetch_all_cases(base: str, opener, csrf: str, sat_field: str,
                     date_from: str | None, date_to: str | None) -> tuple[list[dict], bool]:
    """All Cases in the date window (for closed-by-IC + survey scores).

    Tries to $expand the satisfaction lookup; if the instance uses a different property name the
    query 400s, so we retry WITHOUT it and report survey data as unavailable (survey_ok=False)
    rather than failing the whole pull.
    """
    select = "Id,Number,CreatedOn,ModifiedById"
    base_expand = "Status($select=Name),Owner($select=Id,Name),Group($select=Name)"
    filt = "1 eq 1" + _date_filter(date_from, date_to)
    try:
        expand = f"{base_expand},{sat_field}($select=Name)"
        return _page_cases(base, opener, csrf, select, expand, filt), True
    except urllib.error.HTTPError as e:
        if e.code != 400:
            raise
        # Unknown satisfaction property -> degrade gracefully, keep everything else working.
        return _page_cases(base, opener, csrf, select, base_expand, filt), False


def _fetch_drafted_cases(base: str, opener, csrf: str,
                         date_from: str | None, date_to: str | None) -> list[dict]:
    """Cases that have an AI draft (UsrAiDraftText ne null) in the date window - the adoption universe."""
    select = "Id,Number,CreatedOn,ModifiedById,UsrAiApproved"
    expand = "Status($select=Name),Owner($select=Id,Name),Group($select=Name)"
    filt = "UsrAiDraftText ne null" + _date_filter(date_from, date_to)
    return _page_cases(base, opener, csrf, select, expand, filt)


# --------------------------------------------------------------------------- #
# Row helpers                                                                  #
# --------------------------------------------------------------------------- #
def _is_done(r: dict) -> bool:
    """Terminal status = the case is closed (closed / resolved / cancelled)."""
    n = ((r.get("Status") or {}).get("Name") or "").lower()
    return any(x in n for x in ("clos", "resolv", "cancel"))


def _is_true(r: dict, k: str) -> bool:
    return r.get(k) is True


def _attribute(r: dict) -> str:
    """Who owns this case: the Owner if set, else whoever last modified/closed it stays 'Unassigned'
    (we only have ModifiedById, not a name, without an extra lookup - Owner covers ~all closed cases)."""
    owner = r.get("Owner") or {}
    oid = owner.get("Id")
    if oid and oid != NULL_GUID:
        return owner.get("Name") or "Unassigned"
    return "Unassigned"


def _sat_name(r: dict, sat_field: str) -> str | None:
    node = r.get(sat_field) or {}
    name = (node.get("Name") or "").strip()
    return name or None


# --------------------------------------------------------------------------- #
# Aggregation                                                                  #
# --------------------------------------------------------------------------- #
def _blank_ic() -> dict:
    return {
        "closed": 0,
        # survey
        "survey_responses": 0,
        "promoters": 0,
        "detractors": 0,
        "neutral": 0,
        "score_sum": 0,
        "distribution": {"Excellent": 0, "Good": 0, "Neutral": 0, "Poor": 0, "Extremely poor": 0},
        # adoption (closed cases with an AI draft)
        "drafted_closed": 0,
        "approved_closed": 0,
    }


def _distinct_days(rows: list[dict], date_from: str | None, date_to: str | None) -> int:
    """Number of calendar days in the window - used for a per-day average of closed tickets."""
    if date_from and date_to:
        try:
            d0 = date.fromisoformat(date_from)
            d1 = date.fromisoformat(date_to)
            return max((d1 - d0).days + 1, 1)
        except ValueError:
            pass
    days = {(r.get("CreatedOn") or "")[:10] for r in rows if r.get("CreatedOn")}
    days.discard("")
    return max(len(days), 1)


def collect(creds: dict | None = None, date_from: str | None = None,
            date_to: str | None = None, team_only: bool = True) -> dict:
    """Log in, pull, aggregate. Returns the dashboard payload (see the keys built at the bottom)."""
    env = creds or load_env()
    base = env["CREATIO_URL"].rstrip("/")
    sat_field = (env.get("CREATIO_SATISFACTION_FIELD") or DEFAULT_SATISFACTION_FIELD).strip()

    opener, csrf = login(base, env["CREATIO_USER"], env["CREATIO_PASS"])
    all_rows, survey_ok = _fetch_all_cases(base, opener, csrf, sat_field, date_from, date_to)
    drafted_rows = _fetch_drafted_cases(base, opener, csrf, date_from, date_to)

    ic: dict[str, dict] = defaultdict(_blank_ic)
    ic_level: dict[str, str] = {}

    def bump_level(name: str) -> bool:
        """Record the IC's level; return True if they're on the support roster."""
        m = _match_roster(name)
        if m:
            ic_level[name] = m[1]
            return True
        ic_level.setdefault(name, (all_rows and "Other") or "Other")
        return False

    # --- 1) Tickets closed by IC  +  2) survey scores (over all cases in window) ---
    survey_overall = Counter()
    for r in all_rows:
        person = _attribute(r)
        if person == "Unassigned":
            continue
        on_team = bump_level(person)
        if team_only and not on_team:
            continue
        rec = ic[person]
        if _is_done(r):
            rec["closed"] += 1
        if survey_ok:
            sname = _sat_name(r, sat_field)
            if sname:
                key = sname.strip()
                low = key.lower()
                rec["survey_responses"] += 1
                rec["score_sum"] += SATISFACTION_SCALE.get(low, 0)
                if key in rec["distribution"]:
                    rec["distribution"][key] += 1
                if low in PROMOTERS:
                    rec["promoters"] += 1
                elif low in DETRACTORS:
                    rec["detractors"] += 1
                else:
                    rec["neutral"] += 1
                survey_overall[key if key in rec["distribution"] else "Other"] += 1

    # --- 3) AI-agent adoption over CLOSED cases only ---
    for r in drafted_rows:
        if not _is_done(r):
            continue                      # adoption looks ONLY at tickets that have been closed
        person = _attribute(r)
        if person == "Unassigned":
            # still count toward the overall adoption universe, just not to a person
            person = "Unassigned"
        else:
            on_team = bump_level(person)
            if team_only and not on_team:
                continue
        rec = ic[person]
        rec["drafted_closed"] += 1
        if _is_true(r, "UsrAiApproved"):
            rec["approved_closed"] += 1

    ic.pop("Unassigned", None)  # not an IC; drop from the per-person table

    days = _distinct_days(all_rows, date_from, date_to)

    def nps(rec: dict) -> float | None:
        n = rec["survey_responses"]
        return round((rec["promoters"] - rec["detractors"]) / n * 100, 1) if n else None

    def csat(rec: dict) -> float | None:
        n = rec["survey_responses"]
        return round(rec["score_sum"] / n, 2) if n else None

    def adoption(rec: dict) -> float | None:
        d = rec["drafted_closed"]
        return round(rec["approved_closed"] / d, 4) if d else None

    by_ic = []
    for name, rec in ic.items():
        by_ic.append({
            "name": name,
            "level": ic_level.get(name, "Other"),
            "closed": rec["closed"],
            "avg_closed_per_day": round(rec["closed"] / days, 2),
            "survey_responses": rec["survey_responses"],
            "nps": nps(rec),
            "csat": csat(rec),
            "promoters": rec["promoters"],
            "detractors": rec["detractors"],
            "neutral": rec["neutral"],
            "distribution": rec["distribution"],
            "drafted_closed": rec["drafted_closed"],
            "approved_closed": rec["approved_closed"],
            "adoption_rate": adoption(rec),
        })
    by_ic.sort(key=lambda x: (-x["closed"], x["name"]))

    # Overall roll-ups
    tot_closed = sum(x["closed"] for x in by_ic)
    tot_resp = sum(x["survey_responses"] for x in by_ic)
    tot_prom = sum(x["promoters"] for x in by_ic)
    tot_detr = sum(x["detractors"] for x in by_ic)
    tot_neu = sum(x["neutral"] for x in by_ic)
    tot_score = sum(SATISFACTION_SCALE.get(k.lower(), 0) * v
                    for x in by_ic for k, v in x["distribution"].items())
    tot_drafted_closed = sum(x["drafted_closed"] for x in by_ic)
    tot_approved_closed = sum(x["approved_closed"] for x in by_ic)

    overall_dist = {k: 0 for k in ("Excellent", "Good", "Neutral", "Poor", "Extremely poor")}
    for x in by_ic:
        for k, v in x["distribution"].items():
            overall_dist[k] += v

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "range": {"from": date_from, "to": date_to, "days": days},
        "team_only": team_only,
        "survey_available": survey_ok,
        "satisfaction_field": sat_field,
        "totals": {
            "closed": tot_closed,
            "survey_responses": tot_resp,
            "nps": round((tot_prom - tot_detr) / tot_resp * 100, 1) if tot_resp else None,
            "csat": round(tot_score / tot_resp, 2) if tot_resp else None,
            "promoters": tot_prom,
            "detractors": tot_detr,
            "neutral": tot_neu,
            "distribution": overall_dist,
            "drafted_closed": tot_drafted_closed,
            "approved_closed": tot_approved_closed,
            "adoption_rate": round(tot_approved_closed / tot_drafted_closed, 4)
            if tot_drafted_closed else None,
        },
        "by_ic": by_ic,
    }
