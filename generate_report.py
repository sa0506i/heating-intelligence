#!/usr/bin/env python3
"""
Weekly Heating Industry Intelligence Report Generator
Two-phase approach:
  Phase 1 — Research: Claude searches the web, returns raw findings as plain text (cheap)
  Phase 2 — Synthesis: Claude converts findings to structured JSON (no web search, no loop)
"""

import os
import json
import datetime
import pathlib
import sys
import urllib.request
import urllib.error
import time

# ── CONFIG ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL       = "claude-sonnet-4-6"
REPORTS_DIR = pathlib.Path("reports")

# Phase 1: enough for web search + plain-text findings summary
RESEARCH_MAX_TOKENS = 8000
# Phase 2: JSON output only — findings are already summarised
SYNTHESIS_MAX_TOKENS = 6000

# ── SYSTEM PROMPTS ──────────────────────────────────────────────────────────
RESEARCH_SYSTEM = """You are a research assistant for the residential heating industry.
Your job is to search the web and collect raw findings — nothing else.

DATE RULE: Only include items published between {date_from} and {date_to}.
Verify the date of every item before including it. Discard anything older or undated.

Output a plain numbered list. For each finding write exactly:
TITLE: <exact headline or press release title>
SOURCE: <organisation or publication name>
DATE: <YYYY-MM-DD>
URL: <direct link to the original page>
MARKET: <DE / NL / UK / IT / ES / EU / Global>
FACT: <one sentence — the single most specific fact, number, or claim>

No prose. No sections. No JSON. Just the numbered list."""

SYNTHESIS_SYSTEM = """You are a senior industry analyst for residential heating (boilers, hybrid heat pumps, heat pumps, controllers, IoT).
You receive a list of verified research findings and must convert them into a structured JSON report.
You MUST respond with ONLY valid JSON — no markdown, no explanation, no preamble.
Previous week topics to skip (do not repeat): {prev_titles}"""

# ── PHASE 1: RESEARCH PROMPT ────────────────────────────────────────────────
def build_research_prompt(today: datetime.date) -> str:
    date_from = (today - datetime.timedelta(days=7)).isoformat()
    date_to   = today.isoformat()
    return f"""Today is {date_to}. Find items published between {date_from} and {date_to} only.

Search for:
1. EU/national heating legislation (GEG, EPBD, Boiler Plus UK, EED, Dutch/Italian/Iberian heating rules)
2. Heating norms updated (EN 14511, EN 12309, DIN, BSI, CEN TC 113)
3. Competitor press releases: Bosch/Buderus, Vaillant, Viessmann/Carrier, Worcester Bosch, Baxi/BDR Thermea/Remeha, Ariston, Ferroli, Daikin, Mitsubishi Ecodan, LG ThermaV, Samsung, Ideal Heating, Atlantic/De Dietrich
4. Trade body statements: EHPA, EHI, ZVSHK, BVF, BEAMA, HPA, Assotermica, Techniek Nederland, IDAE
5. New market reports or sales data (BSRIA, EHPA stats, national installer associations)
6. Reddit/YouTube trending topics about heat pumps, boilers, heating costs

Return a plain numbered list of findings using the exact format specified."""

# ── PHASE 2: SYNTHESIS PROMPT ───────────────────────────────────────────────
SYNTHESIS_USER_TEMPLATE = """Convert these verified findings into the JSON report.
Only use what is in the findings list below — do not invent or add items.

FINDINGS:
{findings}

Output this exact JSON structure:
{{
  "executive_summary": "3-4 sentences on the most important specific developments. Name actual products, laws, companies.",
  "signals": {{
    "regulatory_pressure": "High/Medium/Low",
    "market_momentum": "High/Medium/Low",
    "competitor_activity": "High/Medium/Low",
    "social_buzz": "High/Medium/Low"
  }},
  "sections": {{
    "legislation":        [{{"title":"","source":"","market":"","date":"","url":"","summary":""}}],
    "norms":              [{{"title":"","source":"","market":"","date":"","url":"","summary":""}}],
    "competitors":        [{{"title":"","source":"","market":"","date":"","url":"","summary":""}}],
    "market":             [{{"title":"","source":"","market":"","date":"","url":"","summary":""}}],
    "trade_associations": [{{"title":"","source":"","market":"","date":"","url":"","summary":""}}],
    "social_left":        [{{"title":"","source":"","market":"","date":"","url":"","summary":""}}],
    "social_right":       [{{"title":"","source":"","market":"","date":"","url":"","summary":""}}]
  }},
  "portfolio_implications": "3 paragraphs: (1) regulatory impact on boiler/HP portfolio, (2) specific competitor threats or gaps, (3) one recommended action.",
  "week_headline": "8-12 word headline for the most important event this week.",
  "week_preview": "One sentence max 20 words."
}}

Rules:
- 3-5 items per section. If no findings match a section, use {{"title":"No confirmed updates this week","source":"","market":"","date":"{today}","url":null,"summary":"No verified items found this week."}}
- summary field: 2-3 sentences, specific, no generic statements.
- Place social findings evenly between social_left and social_right."""

# ── RAW API CALL ─────────────────────────────────────────────────────────────
def _api_call(api_key: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=data,
        headers={
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"API error {e.code}: {e.read().decode()}")


# ── PHASE 1: run research loop ───────────────────────────────────────────────
def run_research(api_key: str, today: datetime.date) -> str:
    """Run agentic web-search loop. Returns plain-text findings."""
    date_from = (today - datetime.timedelta(days=7)).isoformat()
    date_to   = today.isoformat()
    system    = RESEARCH_SYSTEM.format(date_from=date_from, date_to=date_to)
    messages  = [{"role": "user", "content": build_research_prompt(today)}]
    accumulated = []

    for i in range(25):
        print(f"    Research call {i+1}...")
        raw         = _api_call(api_key, {
            "model":      MODEL,
            "max_tokens": RESEARCH_MAX_TOKENS,
            "system":     system,
            "tools":      [{"type": "web_search_20250305", "name": "web_search"}],
            "messages":   messages,
        })
        stop_reason = raw.get("stop_reason", "")
        content     = raw.get("content", [])

        for block in content:
            if block.get("type") == "text" and block.get("text","").strip():
                accumulated.append(block["text"])

        messages.append({"role": "assistant", "content": content})

        if stop_reason == "end_turn":
            break
        if stop_reason == "tool_use":
            tool_results = [
                {"type": "tool_result", "tool_use_id": b["id"], "content": ""}
                for b in content if b.get("type") == "tool_use"
            ]
            messages.append({"role": "user", "content": tool_results})
            time.sleep(3)
            continue
        if stop_reason == "max_tokens":
            messages.append({"role": "user", "content": "Continue the findings list."})
            time.sleep(3)
            continue
        raise RuntimeError(f"Unexpected stop_reason in research: {stop_reason!r}")

    return "\n".join(accumulated).strip()


# ── PHASE 2: synthesise into JSON ────────────────────────────────────────────
def run_synthesis(api_key: str, findings: str, prev_titles: list, today: datetime.date) -> dict:
    """Single API call (no tools) — convert findings to structured JSON."""
    prev_str  = ", ".join(prev_titles[:30]) if prev_titles else "none"
    system    = SYNTHESIS_SYSTEM.format(prev_titles=prev_str)
    user_msg  = SYNTHESIS_USER_TEMPLATE.format(
        findings=findings,
        today=today.isoformat(),
    )
    accumulated = []

    for i in range(5):
        print(f"    Synthesis call {i+1}...")
        raw = _api_call(api_key, {
            "model":      MODEL,
            "max_tokens": SYNTHESIS_MAX_TOKENS,
            "system":     system,
            "messages":   [{"role": "user", "content": user_msg}],
        })
        stop_reason = raw.get("stop_reason", "")
        content     = raw.get("content", [])

        for block in content:
            if block.get("type") == "text" and block.get("text","").strip():
                accumulated.append(block["text"])

        if stop_reason == "end_turn":
            break
        if stop_reason == "max_tokens":
            # Very unlikely at 6k tokens for JSON-only output, but handle gracefully
            user_msg = "Continue exactly from where you left off."
            time.sleep(3)
            continue
        raise RuntimeError(f"Unexpected stop_reason in synthesis: {stop_reason!r}")

    full_text = "".join(accumulated).strip()
    if full_text.startswith("```"):
        full_text = full_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return json.loads(full_text)


# ── HELPERS ──────────────────────────────────────────────────────────────────
def get_iso_week():
    today = datetime.date.today()
    year, week, _ = today.isocalendar()
    return year, week

def get_report_filename(year, week):
    return f"{year}-W{week:02d}.json"

def load_previous_report(index: dict) -> dict | None:
    reports = index.get("reports", [])
    if not reports:
        return None
    p = REPORTS_DIR / reports[0].get("file", "")
    return json.loads(p.read_text()) if p.exists() else None

def load_index() -> dict:
    p = REPORTS_DIR / "index.json"
    return json.loads(p.read_text()) if p.exists() else {"reports": []}

def save_index(index: dict):
    (REPORTS_DIR / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False))

def save_report(report_data: dict, filename: str):
    REPORTS_DIR.mkdir(exist_ok=True)
    p = REPORTS_DIR / filename
    p.write_text(json.dumps(report_data, indent=2, ensure_ascii=False))
    print(f"  Saved: {p}")

def update_index(index, filename, year, week, edition, report):
    entry = {
        "file":     filename,
        "edition":  str(edition),
        "date":     datetime.date.today().isoformat(),
        "week":     f"{year}-W{week:02d}",
        "headline": report.get("week_headline", "Heating Intelligence Weekly"),
        "preview":  report.get("week_preview", ""),
    }
    index["reports"] = [entry] + [r for r in index["reports"] if r["file"] != filename]
    return index


# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    year, week = get_iso_week()
    filename   = get_report_filename(year, week)
    today      = datetime.date.today()
    print(f"Generating report for {year}-W{week:02d}...")

    REPORTS_DIR.mkdir(exist_ok=True)
    index   = load_index()
    edition = len(index["reports"]) + 1

    existing = [r for r in index["reports"] if r.get("week") == f"{year}-W{week:02d}"]
    if existing and "--force" not in sys.argv:
        print(f"  Report for {year}-W{week:02d} already exists. Use --force to regenerate.")
        sys.exit(0)

    prev_report  = load_previous_report(index)
    prev_titles  = []
    if prev_report:
        for items in prev_report.get("sections", {}).values():
            if isinstance(items, list):
                prev_titles += [i["title"] for i in items if isinstance(i, dict) and i.get("title")]
        print(f"  Previous report loaded ({len(prev_titles)} items to skip).")
    else:
        print("  No previous report — first run.")

    # Phase 1 — Research
    print("  Phase 1: researching...")
    findings = run_research(ANTHROPIC_API_KEY, today)
    print(f"  Findings: {len(findings.split(chr(10)))} lines collected.")

    # Phase 2 — Synthesis
    print("  Phase 2: synthesising JSON...")
    report = run_synthesis(ANTHROPIC_API_KEY, findings, prev_titles, today)
    print("  Report generated.")

    save_report(report, filename)
    index = update_index(index, filename, year, week, edition, report)
    save_index(index)
    print(f"  Done. Total reports in archive: {len(index['reports'])}")

if __name__ == "__main__":
    main()
