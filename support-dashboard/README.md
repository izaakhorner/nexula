# Support Performance Dashboard

A small, local dashboard that replaces the manual "daily closure" spreadsheet with live
numbers pulled straight from Creatio. It shows exactly three things, per support agent (IC)
and as a team total:

1. **Tickets closed by IC** — closed / resolved / cancelled cases, attributed to the owner.
2. **Survey scores** — the Case *Satisfaction level* field, scored as NPS + average CSAT.
3. **AI-agent adoption** — of the **closed** tickets that had an AI draft, how many actually
   used the draft. *Adoption is measured over closed tickets only, by design.*

`serve.py` runs a tiny local web server (Python standard library only — no `pip install`).
The browser only ever sees the aggregate numbers; your Creatio login is validated once and
held in the server's memory for the session — **never written to disk, never sent to the
browser**.

---

## Run it

```bash
# from this folder — Python 3.11+
python3 serve.py
```

Then open <http://localhost:8791>.

On first load it asks for your **Creatio URL / username / password**. Enter them and click
**Connect** — they're validated with a real login and kept in memory only. Use **Refresh**
any time; change the **From / To** dates or untick **Support team only** to widen the view.

Prefer a file? Copy `.env.example` to `.env`, fill in `CREATIO_USER` / `CREATIO_PASS`, and
restart. `.env` is gitignored and never leaves your machine.

---

## How it connects to Creatio

This is the same proven prod-auth flow the metric board uses:

1. **Session login** — `POST {CREATIO_URL}/ServiceModel/AuthService.svc/Login` with
   `{"UserName", "UserPassword"}`. On success Creatio sets a session cookie and a `BPMCSRF`
   cookie.
2. **Authenticated OData** — every read is `GET {CREATIO_URL}/0/odata/Case?...` sent with the
   cookie jar plus two headers: `BPMCSRF: <value>` and `ForceUseSession: true`.
3. Results are paged 1000 rows at a time (`$top` / `$skip`).

All of this lives in `metrics.py` (`login()`, `_get()`, `_page_cases()`), so it's easy to
extend to other Creatio entities later.

## How each metric is computed

| Metric | Source | Definition |
|--------|--------|-----------|
| Tickets closed by IC | `Case.Status`, `Case.Owner` | count of cases whose status is closed / resolved / cancelled, grouped by owner |
| Survey score (NPS) | `Case.SatisfactionLevel.Name` | `(promoters − detractors) / responses × 100`; promoters = Excellent + Good, detractors = Poor + Extremely poor |
| Avg CSAT | `Case.SatisfactionLevel.Name` | mean on a 1–5 scale (Excellent 5 … Extremely poor 1) |
| AI adoption (closed only) | `Case.UsrAiDraftText`, `Case.UsrAiApproved`, `Case.Status` | of **closed** cases with a draft, the share where the draft was approved/used |

The NPS formula intentionally matches the methodology already used in the spreadsheet, so the
numbers stay comparable.

### Notes

- The satisfaction lookup is expanded defensively. If your instance uses a different property
  name than `SatisfactionLevel`, the pull still succeeds (closed + adoption keep working) and
  the survey section shows a note telling you to set the right field — do that in the
  Credentials dialog or via `CREATIO_SATISFACTION_FIELD` in `.env`.
- Default date range is **month-to-date**. Change it with the From / To pickers.
- The **support team** roster and each IC's level are in `SUPPORT_ROSTER` at the top of
  `metrics.py`. Edit that list when the team changes.

## Files

```
serve.py         local web server + credential handling (stdlib only)
metrics.py       Creatio connection + the three metric roll-ups
index.html       the dashboard UI (single page)
.env.example     credential template — copy to .env
```

## Security

- No credentials ship in this folder. Enter your own; keep them in `.env` (gitignored) or the
  in-memory Credentials box.
- The dashboard reads **live production support data**. Keep it on your machine / trusted
  network — don't put it behind a public tunnel without authentication.
