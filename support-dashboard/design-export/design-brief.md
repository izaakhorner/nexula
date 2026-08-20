# Design brief — Support Performance Dashboard

**Use this with Claude Design.** Paste this brief and attach `dashboard-data.json`. Claude Design
will produce artboard(s) you can refine visually, then hand the result back into the Claude Code
session (see *Round-trip* at the bottom) so it gets implemented into the real, live dashboard.

## What this is

A single-screen internal dashboard for the H&L support team. It replaces a manual spreadsheet.
It shows **three things**, plus a KPI summary row. Everything is read-only — no forms, no inputs
except a date range and a "support team only" toggle in the header.

## The data

All numbers live in `dashboard-data.json`:

- `kpis[]` — the four summary tiles (tickets closed, survey NPS, avg CSAT, AI adoption).
- `by_ic[]` — one row per support agent (the "IC"), with closed count, survey breakdown, and
  adoption figures.
- `overall` — team totals.
- `metric_definitions` — plain-English meaning of each metric (use as tooltip/caption copy).
- `palette_hint` — a neutral dark palette to start from; swap for H&L brand colours.

> **Data quality:** `closed` and `survey` figures are **real** (Aug 2026, month-to-date).
> `adoption` values are **illustrative sample data** — label them subtly as sample in the design,
> or don't over-emphasise them, since they'll be replaced by live Creatio numbers.

## Sections to design (in order)

1. **Header** — title "Support Performance Dashboard", a subtitle, a date-range control
   (From / To), a "Support team only" toggle, and a Refresh action. Show the reporting period.

2. **KPI row** — the four `kpis[]` as stat tiles. Tickets closed (996), Survey NPS (71.4),
   Avg CSAT (4.29 / 5), AI adoption (66% — sample). Make these scannable and confident.

3. **Tickets closed by IC** — ranked list/table of `by_ic[]` by `closed`. Show name, level
   (L1/L2), vendor, closed count, and avg/day. A horizontal bar per agent reads well here.

4. **Survey scores** — only agents with `survey_responses > 0`. Show NPS, CSAT, and the
   Excellent → Extremely-poor distribution. A small stacked/diverging bar of the distribution
   would be more interesting than raw counts. Colour Excellent/Good positive, Poor/Extremely-poor
   negative.

5. **AI-agent adoption (closed tickets only)** — `by_ic[]` sorted by `adoption_rate`. Show
   closed-with-draft, draft-used, and the adoption %. Emphasise it's measured over closed tickets.

## Style direction

- Dense but calm; this is a daily operational tool, not a marketing page.
- Dark theme to start (see `palette_hint`), but a light variant is welcome.
- Prefer real visual interest over plain tables: bars, a distribution strip, subtle rank cues,
  a clear visual hierarchy from KPIs → sections.
- Keep it to **one screen / one artboard** if you can (a tall scroll is fine). Desktop-first,
  ~1200px content width.
- Accessible contrast; don't rely on colour alone for the survey good/bad split.

## What NOT to add

No voice-call metrics, no QA benchmark, no per-day time series, no login screen. Just the three
sections above. Keep the scope tight — this mirrors exactly what the live dashboard computes.

## Round-trip — bringing it back into this session

Once you like the design in Claude Design, hand it back here in **either** form and ask me to
"implement this into the dashboard":

- **Export the artboard HTML/CSS** (Claude Design can export) and paste or attach it, **or**
- Paste the **published Claude Design / Artifact URL** — I can fetch it.

I'll then translate the visual into the real `index.html` (which renders live `dashboard-data.json`
/ Creatio output), preserving the exact data bindings and metric definitions so the styling lands
on real numbers.
