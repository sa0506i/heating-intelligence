#!/usr/bin/env python3
"""
Weekly Heating Industry Intelligence Report Generator
Calls Claude API with web search → saves JSON report → updates index
Runs every Monday 08:00 CET via GitHub Actions
"""

import os
import json
import datetime
import pathlib
import sys
import urllib.request
import urllib.error

# ── CONFIG ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-20250514"
REPORTS_DIR = pathlib.Path("reports")
MAX_TOKENS = 4000

SYSTEM_PROMPT = """You are a senior industry analyst assistant specializing in the residential heating sector.
You are generating a structured weekly intelligence report for two senior executives:
1. Head of Portfolio and Product Management — Boilers, Hybrid Heat Pumps, Heat Pumps (EU)
2. Head of Engineering

Focus markets: Germany, Netherlands, UK, Italy, Iberia (Spain + Portugal), and broader EU.
Products: Gas boilers, hybrid heat pumps, full heat pumps, heating controllers, IoT/connected heating systems.

You MUST respond with ONLY valid JSON. No markdown, no explanation, no preamble.
Follow the exact schema provided in the user message."""

USER_PROMPT = """Search the web and generate this week's residential heating industry intelligence report.

Search for information from the past 7 days on:
1. EU and national legislation updates (ErP, EED, F-Gas, Building Renovation, Germany GEG, UK Boiler Plus, NL, Italy, Iberia)
2. New or updated norms and standards (EN standards related to boilers, heat pumps, controls)
3. Competitor news: Bosch, Vaillant, Viessmann, Worcester Bosch, Baxi, Rinnai, Daikin, Mitsubishi, Samsung, LG, Ariston, Ferroli, BDR Thermea, Ideal Heating, Atlantic, De Dietrich — product launches, announcements, partnerships, M&A
4. Market reports: new releases from Wood Mackenzie, BSRIA, Freedonia, EHPA, BVF, ZVSHK, etc.
5. Social media trends: Reddit (r/heatpumps, r/DIY, r/HVAC, r/Germany etc.), YouTube trending videos, Instagram/TikTok topics related to heat pumps, boilers, heating costs

Respond ONLY with this exact JSON structure (no markdown, no backticks, just raw JSON):

{
  "executive_summary": "3-4 sentence high-level summary of the most important developments this week, highlighting what matters most for portfolio management and engineering decisions.",

  "signals": {
    "regulatory_pressure": "High/Medium/Low",
    "market_momentum": "High/Medium/Low",
    "competitor_activity": "High/Medium/Low",
    "social_buzz": "High/Medium/Low"
  },

  "sections": {
    "legislation": [
      {
        "title": "Title of the update",
        "source": "Source name",
        "market": "DE / NL / UK / IT / ES / EU",
        "date": "YYYY-MM-DD or 'this week'",
        "summary": "2-3 sentences explaining what happened and why it matters for boiler/heat pump portfolio."
      }
    ],
    "norms": [
      {
        "title": "Title",
        "source": "e.g. CEN, DIN, BSI",
        "market": "EU / DE / UK",
        "date": "YYYY-MM-DD or 'this week'",
        "summary": "What changed and engineering relevance."
      }
    ],
    "competitors": [
      {
        "title": "Company: what happened",
        "source": "Source",
        "market": "Market",
        "date": "date",
        "summary": "What they announced/launched and competitive implication."
      }
    ],
    "market": [
      {
        "title": "Report/data title",
        "source": "Publisher",
        "market": "Region",
        "date": "date",
        "summary": "Key findings and market implication."
      }
    ],
    "social_left": [
      {
        "title": "Topic/trend name",
        "source": "Reddit / YouTube / Instagram",
        "market": "Global / DE / UK / EU",
        "date": "this week",
        "summary": "What consumers are saying/watching and what it signals for product strategy."
      }
    ],
    "social_right": [
      {
        "title": "Topic/trend name",
        "source": "Reddit / YouTube / Instagram",
        "market": "Global / DE / UK / EU",
        "date": "this week",
        "summary": "Consumer insight and relevance."
      }
    ]
  },

  "portfolio_implications": "2-3 paragraphs specifically addressing: (1) What this week's news means for the boiler and hybrid heat pump portfolio, (2) Engineering priorities or risks to watch, (3) Recommended actions or decisions to consider.",

  "week_headline": "A short, punchy 8-12 word headline summarizing the most important theme of this week.",
  "week_preview": "One sentence (max 20 words) preview for the archive listing."
}

Include 3-5 items per section. If nothing notable happened in a section, include 1 item noting the quiet week."""

# ── HELPERS ───────────────────────────────────────────────────────────────────

def get_iso_week():
    today = datetime.date.today()
    year, week, _ = today.isocalendar()
    return year, week

def get_report_filename(year, week):
    return f"{year}-W{week:02d}.json"

def call_claude_api(api_key: str) -> dict:
    """Call Anthropic API with web search tool enabled."""
    payload = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        "messages": [{"role": "user", "content": USER_PROMPT}]
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=data,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "interleaved-thinking-2025-05-14",
            "content-type": "application/json",
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        raise RuntimeError(f"API error {e.code}: {body}")

    # Extract text from response (may contain tool_use blocks)
    text_parts = [block["text"] for block in raw.get("content", []) if block.get("type") == "text"]
    full_text = "\n".join(text_parts).strip()

    # Strip accidental markdown fences
    if full_text.startswith("```"):
        full_text = full_text.split("\n", 1)[-1]
        full_text = full_text.rsplit("```", 1)[0]

    return json.loads(full_text)

def load_index() -> dict:
    index_path = REPORTS_DIR / "index.json"
    if index_path.exists():
        return json.loads(index_path.read_text())
    return {"reports": []}

def save_index(index: dict):
    index_path = REPORTS_DIR / "index.json"
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False))

def save_report(report_data: dict, filename: str, year: int, week: int, edition: int):
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / filename
    path.write_text(json.dumps(report_data, indent=2, ensure_ascii=False))
    print(f"  Saved report: {path}")

def update_index(index: dict, filename: str, year: int, week: int, edition: int, report: dict):
    date_str = datetime.date.today().isoformat()
    entry = {
        "file": filename,
        "edition": str(edition),
        "date": date_str,
        "week": f"{year}-W{week:02d}",
        "headline": report.get("week_headline", "Heating Intelligence Weekly"),
        "preview": report.get("week_preview", ""),
    }
    # Prepend (newest first)
    index["reports"] = [entry] + [r for r in index["reports"] if r["file"] != filename]
    return index

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY environment variable is not set.")
        sys.exit(1)

    year, week = get_iso_week()
    filename = get_report_filename(year, week)
    print(f"Generating report for {year}-W{week:02d}...")

    # Load existing index
    REPORTS_DIR.mkdir(exist_ok=True)
    index = load_index()
    edition = len(index["reports"]) + 1

    # Check if already generated this week
    existing = [r for r in index["reports"] if r.get("week") == f"{year}-W{week:02d}"]
    if existing and "--force" not in sys.argv:
        print(f"  Report for {year}-W{week:02d} already exists. Use --force to regenerate.")
        sys.exit(0)

    # Call Claude
    print("  Calling Claude API with web search...")
    report = call_claude_api(ANTHROPIC_API_KEY)
    print("  Report received.")

    # Save
    save_report(report, filename, year, week, edition)
    index = update_index(index, filename, year, week, edition, report)
    save_index(index)
    print(f"  Index updated. Total reports: {len(index['reports'])}")
    print("Done!")

if __name__ == "__main__":
    main()
