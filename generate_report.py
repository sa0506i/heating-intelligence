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
MODEL = "claude-opus-4-6"
REPORTS_DIR = pathlib.Path("reports")
MAX_TOKENS = 4000

SYSTEM_PROMPT = """You are a senior industry analyst assistant specializing in the residential heating sector.
You generate a structured weekly intelligence report for two senior executives:
1. Head of Portfolio and Product Management — Boilers, Hybrid Heat Pumps, Heat Pumps (EU)
2. Head of Engineering

Focus markets: Germany, Netherlands, UK, Italy, Iberia (Spain + Portugal), and broader EU.
Products: Gas boilers, hybrid heat pumps, full heat pumps, heating controllers, IoT/connected heating systems.

STRICT RULES — violations make the report useless:
- ONLY include items published or announced in the last 7 days. Every item must have an exact date.
- NEVER include general background, market overviews, or evergreen information. Every sentence must describe something specific that happened this week.
- NEVER repeat or rephrase anything from the previous week's report (provided below). If a story continued, only report the NEW development from this week.
- For competitors: find and cite actual press releases or news articles published this week. Name the exact product model, feature, or claim. No general strategy summaries.
- Be specific: name the exact law/article number, product model, report title, or Reddit thread. Vague summaries are not acceptable.
- If a section truly has no new verified items this week, include exactly one entry: title "No confirmed updates this week", with a note on what was searched.

You MUST respond with ONLY valid JSON. No markdown, no explanation, no preamble."""


def build_user_prompt(previous_report: dict | None, today: datetime.date) -> str:
    date_from = (today - datetime.timedelta(days=7)).isoformat()
    date_to = today.isoformat()

    prev_section = ""
    if previous_report:
        prev_titles = []
        for section_items in previous_report.get("sections", {}).values():
            if isinstance(section_items, list):
                for item in section_items:
                    if isinstance(item, dict) and item.get("title"):
                        prev_titles.append(f"- {item['title']}")
        prev_exec = previous_report.get("executive_summary", "")
        prev_section = f"""
PREVIOUS WEEK'S REPORT — do NOT repeat any of these topics or stories, even if still in the news:
Last week's summary: {prev_exec}

Items already covered — skip these entirely:
{chr(10).join(prev_titles[:40])}

"""

    return f"""Today is {date_to}. Search for residential heating industry news published strictly between {date_from} and {date_to}.
{prev_section}
Run the following targeted searches:

1. LEGISLATION & POLICY
Search: "GEG 2025 Änderung", "Wärmegesetz Bundestag", "Boiler Plus UK 2025", "ErP ecodesign heating {date_to[:4]}", "EED buildings directive", "Dutch heating ban update", "Italy heating Superbonus", "Spain heating regulation", "EPBD implementation" — report only official publications, votes, consultations, or government announcements from this week.

2. NORMS & STANDARDS
Search: "EN 14511 2025", "EN 12309 heat pump", "DIN Norm Wärmepumpe", "BSI PAS heating", "CEN TC 113 meeting", "heat pump ErP label" — only new publications, drafts, or consultation openings from this week.

3. COMPETITOR PRESS RELEASES (most important section — do multiple searches per company)
Search each company's recent announcements:
- "Bosch Thermotechnik press release {date_to[:7]}" / "Buderus Neuheit" / "Junkers Bosch announcement"
- "Vaillant press release {date_to[:7]}" / "Vaillant aroTHERM" / "Vaillant ecoTEC"
- "Viessmann Carrier announcement {date_to[:7]}" / "Viessmann Vitocal"
- "Worcester Bosch news {date_to[:7]}"
- "Baxi press release" / "Remeha announcement" / "BDR Thermea news"
- "Ariston press release {date_to[:7]}" / "Ferroli news"
- "Daikin Europe press release {date_to[:7]}" / "Daikin Altherma"
- "Mitsubishi Electric heating announcement {date_to[:7]}" / "Ecodan news"
- "Samsung heat pump announcement" / "LG ThermaV press release"
- "Ideal Heating news" / "Atlantic heating press release"
For each: cite exact product model, specific claim or feature, and press release title or URL.

4. TRADE ASSOCIATION & INDUSTRY BODY PRESS RELEASES
Search the following organisations for press releases, position papers, statistics, or statements published this week:
- EHPA (European Heat Pump Association): "EHPA press release {date_to[:7]}" / "EHPA statement" / site:ehpa.org news
- EHI (European Heating Industry): "EHI press release {date_to[:7]}" / "EHI statement" / site:ehi.eu news
- ZVSHK (Germany — plumbing/heating installers): "ZVSHK Pressemitteilung {date_to[:7]}" / "ZVSHK Stellungnahme"
- BVF (Germany — surface heating): "BVF Pressemitteilung {date_to[:7]}"
- HEA (Heating Equipment Association, UK): "HEA press release {date_to[:7]}"
- BEAMA (UK — manufacturers): "BEAMA press release {date_to[:7]}"
- UNCSAAL / Assotermica (Italy): "Assotermica comunicato {date_to[:7]}"
- AFPAC (France): "AFPAC communiqué {date_to[:7]}"
- Techniek Nederland (NL): "Techniek Nederland persbericht {date_to[:7]}"
- IDAE (Spain — energy agency): "IDAE nota de prensa {date_to[:7]}"
- APISOLAR / AFEC (Iberia — heat pump associations): news from this week
- Heat Pump Association (UK — HPA): "Heat Pump Association press release {date_to[:7]}"
Report the exact title of each press release or statement, the publishing organisation, and the key claim or data point. Do not paraphrase — quote the specific number, policy position, or product category mentioned.

5. MARKET DATA & REPORTS
Search: "heat pump sales {date_to[:7]}", "EHPA statistics {date_to[:4]}", "BSRIA heating report", "boiler sales Germany {date_to[:4]}", "warmtepomp verkopen {date_to[:4]}", "heat pump installations UK {date_to[:4]}", "BVF Marktbericht", "ZVSHK Statistik" — only newly released reports or datasets from this week.

6. SOCIAL MEDIA & CONSUMER TRENDS
Search Reddit (r/heatpumps, r/HVAC, r/germany, r/DIY, r/UKPersonalFinance, r/Wärmepumpe) and YouTube for threads or videos that gained traction this week. Include exact thread or video titles, not summaries of general opinion.

Respond ONLY with this exact JSON (raw JSON, no markdown, no backticks):

{{
  "executive_summary": "3-4 sentences naming specific products, laws, or companies from this week. No generic observations.",

  "signals": {{
    "regulatory_pressure": "High/Medium/Low",
    "market_momentum": "High/Medium/Low",
    "competitor_activity": "High/Medium/Low",
    "social_buzz": "High/Medium/Low"
  }},

  "sections": {{
    "legislation": [
      {{
        "title": "Exact name of law/directive/announcement",
        "source": "Official source + URL if available",
        "market": "DE / NL / UK / IT / ES / PT / EU",
        "date": "YYYY-MM-DD",
        "summary": "What specifically happened this week. Include article numbers or specific provisions. Why it matters for boiler or heat pump portfolio."
      }}
    ],
    "norms": [
      {{
        "title": "Exact norm designation e.g. EN 14511-3:2025 draft",
        "source": "CEN / DIN / BSI / NEN / UNI",
        "market": "EU / DE / UK / NL",
        "date": "YYYY-MM-DD",
        "summary": "What specifically was published or changed. Engineering impact: test conditions, efficiency thresholds, certification implications."
      }}
    ],
    "competitors": [
      {{
        "title": "CompanyName: Exact product model or announcement title",
        "source": "Press release title and URL or news source",
        "market": "DE / UK / EU / Global",
        "date": "YYYY-MM-DD",
        "summary": "Exact product features, specs, pricing, or markets targeted. Direct competitive implication for our hybrid/HP/boiler portfolio."
      }}
    ],
    "market": [
      {{
        "title": "Exact report or dataset title",
        "source": "Publisher name",
        "market": "Region covered",
        "date": "YYYY-MM-DD",
        "summary": "Specific data points (numbers, %, forecasts). What it signals for portfolio or go-to-market planning."
      }}
    ],
    "trade_associations": [
      {{
        "title": "Exact press release or statement title",
        "source": "Organisation name (e.g. EHPA, EHI, ZVSHK, HPA, BEAMA)",
        "market": "EU / DE / UK / IT / ES / NL",
        "date": "YYYY-MM-DD",
        "summary": "Specific claim, statistic, or policy position stated. Why it matters for heating portfolio strategy or regulatory positioning."
      }}
    ],
    "social_left": [
      {{
        "title": "Exact Reddit thread title or YouTube video title",
        "source": "Reddit r/NAME / YouTube channel name",
        "market": "DE / UK / Global / EU",
        "date": "YYYY-MM-DD",
        "summary": "What specifically was discussed or viewed. Consumer pain point or preference signal relevant to product or communication strategy."
      }}
    ],
    "social_right": [
      {{
        "title": "Exact thread/video/trend title",
        "source": "Reddit r/NAME / YouTube / Google Trends",
        "market": "DE / UK / Global / EU",
        "date": "YYYY-MM-DD",
        "summary": "Specific insight. Implication for product features, installer training, or marketing."
      }}
    ]
  }},

  "portfolio_implications": "Paragraph 1: Which specific legislative or regulatory action from this week directly affects boiler phase-out timelines or heat pump incentives — and by how much. Paragraph 2: Specific competitor moves from this week that create a gap or threat — name the product and market. Paragraph 3: One concrete recommended action or decision trigger based solely on this week's intelligence.",

  "week_headline": "8-12 word headline naming the single most important specific event of this week.",
  "week_preview": "One sentence max 20 words for archive listing."
}}

Include 3-5 items per section. If no verified news exists for a section, use exactly one entry with title 'No confirmed updates this week'."""

# ── HELPERS ───────────────────────────────────────────────────────────────────

def get_iso_week():
    today = datetime.date.today()
    year, week, _ = today.isocalendar()
    return year, week

def get_report_filename(year, week):
    return f"{year}-W{week:02d}.json"

def call_claude_api(api_key: str, user_prompt: str) -> dict:
    """Call Anthropic API with web search tool enabled."""
    payload = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        "messages": [{"role": "user", "content": user_prompt}]
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=data,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
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


def load_previous_report(index: dict) -> dict | None:
    """Load the most recent past report to pass as dedupe context."""
    reports = index.get("reports", [])
    if not reports:
        return None
    path = REPORTS_DIR / reports[0].get("file", "")
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


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

    # Load previous report for dedupe context
    previous_report = load_previous_report(index)
    if previous_report:
        print("  Previous report loaded for dedupe context.")
    else:
        print("  No previous report found — first run.")

    # Build dynamic prompt with today's date + previous report context
    today = datetime.date.today()
    user_prompt = build_user_prompt(previous_report, today)

    # Call Claude
    print("  Calling Claude API with web search...")
    report = call_claude_api(ANTHROPIC_API_KEY, user_prompt)
    print("  Report received.")

    # Save
    save_report(report, filename, year, week, edition)
    index = update_index(index, filename, year, week, edition, report)
    save_index(index)
    print(f"  Index updated. Total reports: {len(index['reports'])}")
    print("Done!")

if __name__ == "__main__":
    main()
