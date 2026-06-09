#!/usr/bin/env python3
"""
Transcript Intelligence Engine — Inspection/NDT Sector
=======================================================
Builds advanced analytics from earnings call transcripts and AI summaries:
  F1 — Earnings Season Scorecard (cross-company comparison)
  F2 — Management Tone Shift Detection
  F3 — Analyst Question Clustering
  F4 — Guidance vs Actuals / Credibility Tracker
  F5 — Key Metric Extraction from summaries
  F7 — Comparative Earnings Timeline

Output: Companies/transcript_intel.json

Usage:
  python3 transcript_intelligence.py
  python3 transcript_intelligence.py --quarter Q4_2025
"""

import argparse
import csv
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent  # Inspection_Intel/
RESEARCH_DIR = PROJECT_DIR / "Companies"
INDUSTRY_DATA_DIR = PROJECT_DIR / "Industry_Data" / "Transcript_Analysis"
SUMMARIES_FILE = RESEARCH_DIR / "transcript_summaries.json"
TRANSCRIPT_CSV = INDUSTRY_DATA_DIR / "transcript_summary.csv"
GUIDANCE_CSV = INDUSTRY_DATA_DIR / "guidance_tracker.csv"
COMPANIES_FILE = SCRIPT_DIR / "edgar_company_registry.json"
OUTPUT_FILE = RESEARCH_DIR / "transcript_intel.json"

# NDT universe tickers (display tickers used in transcripts)
# Maps yfinance tickers to display tickers for matching
NDT_UNIVERSE = {
    'MG', 'TISI', 'TIC', 'OII', 'XPRO',
    'BVI', 'ITRK', 'COTN',
    'TRNS', 'THR',
}
# Some transcripts may use OTC/alternative tickers for the European-listed companies
NDT_TICKER_ALIASES = {
    'ITRKY': 'ITRK',    # Intertek ADR ticker
    'BVRDF': 'BVI',     # Bureau Veritas OTC ticker
    'BVI.PA': 'BVI',
    'ITRK.L': 'ITRK',
    'COTN.SW': 'COTN',
    'SGSOF': None,       # SGS — not in universe
    'SGSN': None,        # SGS — not in universe
}

# ── Hedging / Confidence lexicons (F2) ───────────────────────────────────────
HEDGING_WORDS = [
    'cautiously', 'cautious', 'uncertain', 'uncertainty', 'challenging',
    'headwinds', 'headwind', 'visibility limited', 'limited visibility',
    'volatile', 'volatility', 'tempered', 'modest', 'prudent',
    'conservative', 'measured', 'carefully', 'watchful', 'guarded',
    'mindful', 'navigating', 'near-term pressure', 'softer', 'softening',
]

CONFIDENCE_WORDS = [
    'confident', 'confidence', 'strong momentum', 'well-positioned',
    'well positioned', 'robust', 'exceptional', 'outstanding', 'record',
    'accelerating', 'acceleration', 'beat', 'exceeded', 'outperformed',
    'ahead of plan', 'ahead of expectations', 'upside', 'bullish',
    'optimistic', 'enthusiastic', 'transformational', 'inflection',
]

# ── Analyst question theme keywords (F3) — Inspection/NDT-specific ──────────
ANALYST_THEMES = {
    'backlog_pipeline': ['backlog', 'pipeline', 'book-to-bill', 'bookings', 'order',
                         'awarded', 'contract', 'bid', 'funnel', 'demand'],
    'nuclear_services': ['nuclear', 'reactor', 'nrc', 'decommissioning', 'outage',
                         'radiography', 'power plant', 'fuel cycle'],
    'aerospace_defense': ['aerospace', 'defense', 'aviation', 'boeing', 'airbus',
                          'nadcap', 'as9100', 'aircraft', 'engine'],
    'infrastructure_spend': ['infrastructure', 'bridge', 'pipeline', 'rail', 'iija',
                             'data center', 'power grid', 'utility', 'government'],
    'digital_automation': ['digital', 'automation', 'ai', 'drone', 'robot', 'saas',
                           'iot', 'remote inspection', 'phased array', 'software'],
    'margin_profitability': ['margin', 'profitability', 'ebitda', 'cost', 'pricing',
                             'labor', 'utilization', 'efficiency', 'g&a', 'overhead'],
    'ma_consolidation': ['acquisition', 'merger', 'bolt-on', 'integration', 'synergies',
                         'divestiture', 'consolidation', 'pipeline', 'deal'],
    'regulatory_compliance': ['regulation', 'api', 'asme', 'iso', 'certification',
                              'compliance', 'esg', 'safety', 'standard'],
    'international_expansion': ['international', 'global', 'europe', 'asia', 'offshore',
                                'middle east', 'market entry', 'geographic'],
    'capital_allocation': ['capex', 'dividend', 'buyback', 'debt', 'leverage',
                           'free cash flow', 'refinance', 'balance sheet'],
}

# ── Metric extraction patterns (F5) — Inspection-specific ───────────────────
METRIC_PATTERNS = {
    'revenue': [
        r'(?:revenue|revenues|net revenue|total revenue)s?\s+(?:of\s+)?\$?([\d,.]+)\s*(billion|million|B|M|bn|mm)',
        r'\$([\d,.]+)\s*(billion|million|B|M|bn|mm)\s+(?:in\s+)?(?:revenue|revenues|net revenue)',
        r'(?:revenue|revenues)\s+(?:was|were|came in at|totaled|reached)\s+\$?([\d,.]+)\s*(billion|million|B|M|bn|mm)',
    ],
    'eps': [
        r'(?:EPS|earnings per share|diluted EPS|adjusted EPS)\s+(?:of\s+)?\$?([\d,.]+)',
        r'\$([\d,.]+)\s+(?:per share|EPS)',
        r'(?:EPS|earnings per share)\s+(?:was|came in at)\s+\$?([\d,.]+)',
    ],
    'ebitda': [
        r'(?:EBITDA|adjusted EBITDA|Adj\. EBITDA)\s+(?:of\s+)?\$?([\d,.]+)\s*(billion|million|B|M|bn|mm)',
        r'\$([\d,.]+)\s*(billion|million|B|M|bn|mm)\s+(?:in\s+)?(?:EBITDA|adjusted EBITDA)',
    ],
    'free_cash_flow': [
        r'(?:free cash flow|FCF)\s+(?:of\s+)?\$?([\d,.]+)\s*(billion|million|B|M|bn|mm)',
        r'\$([\d,.]+)\s*(billion|million|B|M|bn|mm)\s+(?:in\s+)?(?:free cash flow|FCF)',
    ],
    'capex': [
        r'(?:capex|capital expenditure|capital spending|capital budget)\s+(?:of\s+)?\$?([\d,.]+)\s*(billion|million|B|M|bn|mm)',
        r'\$([\d,.]+)\s*(billion|million|B|M|bn|mm)\s+(?:in\s+)?(?:capex|capital)',
    ],
    'guidance_revenue': [
        r'(?:guidance|expects|targeting|forecast).*?(?:revenue|revenues)\s+(?:of\s+)?\$?([\d,.]+)\s*(billion|million|B|M|bn|mm)',
        r'(?:revenue|revenues)\s+(?:guidance|target|forecast)\s+(?:of\s+)?\$?([\d,.]+)\s*(billion|million|B|M|bn|mm)',
    ],
    'utilization_rate': [
        r'(?:utilization|utilisation)\s+(?:rate\s+)?(?:of\s+)?([\d,.]+)%',
        r'([\d,.]+)%\s+(?:utilization|utilisation)',
    ],
    'organic_growth': [
        r'(?:organic|organic revenue)\s+(?:growth|increase)\s+(?:of\s+)?([\d,.]+)%',
    ],
}


def load_summaries():
    """Load AI-generated transcript summaries."""
    if not SUMMARIES_FILE.exists():
        print(f"  Warning: {SUMMARIES_FILE} not found")
        return {}
    with open(SUMMARIES_FILE) as f:
        return json.load(f)


def load_transcript_csv():
    """Load analyzed transcript data from CSV."""
    if not TRANSCRIPT_CSV.exists():
        print(f"  Warning: {TRANSCRIPT_CSV} not found")
        return []
    with open(TRANSCRIPT_CSV) as f:
        return list(csv.DictReader(f))


def load_guidance_csv():
    """Load guidance tracker data."""
    if not GUIDANCE_CSV.exists():
        return []
    with open(GUIDANCE_CSV) as f:
        return list(csv.DictReader(f))


def load_companies():
    """Load company metadata from JSON registry."""
    companies = {}
    if COMPANIES_FILE.exists():
        with open(COMPANIES_FILE) as f:
            registry = json.load(f)
        entries = registry.get('companies', registry) if isinstance(registry, dict) else registry
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            companies[entry['ticker']] = {
                'company': entry.get('name', entry.get('folder', '').replace('_', ' ')),
                'subsector': entry.get('category', 'Unknown'),
            }
    return companies


def parse_period(key):
    """Parse 'TICKER_Q#_YEAR' key into components."""
    parts = key.split('_')
    if len(parts) >= 3:
        ticker = parts[0]
        quarter = parts[1]
        year = parts[2]
        return ticker, quarter, year
    return None, None, None


def period_sort_key(quarter, year):
    """Create sortable key from Q# and year."""
    try:
        q = int(quarter.replace('Q', ''))
        y = int(year)
        return y * 10 + q
    except (ValueError, AttributeError):
        return 0


# ═══════════════════════════════════════════════════════════════════════════════
# F5 — Key Metric Extraction
# ═══════════════════════════════════════════════════════════════════════════════

def normalize_amount(value_str, unit_str):
    """Convert extracted amount to a display string like '$4.2B' or '$185M'."""
    try:
        value = float(value_str.replace(',', ''))
    except ValueError:
        return None

    unit = unit_str.lower().strip()
    if unit in ('billion', 'b', 'bn'):
        return f"${value:.1f}B" if value < 100 else f"${value:.0f}B"
    elif unit in ('million', 'm', 'mm'):
        if value >= 1000:
            return f"${value / 1000:.1f}B"
        return f"${value:.0f}M" if value >= 10 else f"${value:.1f}M"
    return f"${value_str}"


def extract_metrics_from_summary(summary_text):
    """Extract key financial metrics from an AI-generated summary."""
    metrics = {}

    for metric_name, patterns in METRIC_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, summary_text, re.IGNORECASE)
            if match:
                groups = match.groups()
                if metric_name in ('eps',):
                    metrics[metric_name] = f"${groups[0]}"
                elif metric_name in ('utilization_rate',):
                    metrics[metric_name] = f"{groups[0]}%"
                elif metric_name in ('organic_growth',):
                    metrics[metric_name] = f"{groups[0]}%"
                elif len(groups) >= 2:
                    normalized = normalize_amount(groups[0], groups[1])
                    if normalized:
                        metrics[metric_name] = normalized
                break  # Use first matching pattern

    return metrics


def build_extracted_metrics(summaries):
    """F5: Extract key metrics from all summaries."""
    print("  F5: Extracting key metrics from summaries...")
    extracted = {}
    count = 0

    for key, data in summaries.items():
        summary = data.get('summary', '') if isinstance(data, dict) else data
        if not summary:
            continue

        metrics = extract_metrics_from_summary(summary)
        if metrics:
            extracted[key] = metrics
            count += 1

    print(f"      Extracted metrics from {count} summaries")
    return extracted


# ═══════════════════════════════════════════════════════════════════════════════
# F2 — Management Tone Shift Detection
# ═══════════════════════════════════════════════════════════════════════════════

def count_lexicon(text, lexicon):
    """Count occurrences of lexicon terms in text (case insensitive)."""
    text_lower = text.lower()
    return sum(text_lower.count(term) for term in lexicon)


def build_tone_shifts(summaries, transcript_data):
    """F2: Detect management tone shifts between quarters."""
    print("  F2: Detecting management tone shifts...")

    # Group transcripts by ticker, sorted by period
    by_ticker = defaultdict(list)
    for row in transcript_data:
        tk = row['ticker']
        q = row.get('quarter', '')
        y = row.get('year', '')
        if q and y:
            by_ticker[tk].append(row)

    # Also analyze summaries for hedging/confidence
    summary_by_ticker = defaultdict(list)
    for key, data in summaries.items():
        ticker, quarter, year = parse_period(key)
        if ticker and quarter and year:
            text = data.get('summary', '') if isinstance(data, dict) else ''
            summary_by_ticker[ticker].append({
                'quarter': quarter,
                'year': year,
                'sort_key': period_sort_key(quarter, year),
                'text': text,
            })

    tone_shifts = {}
    alerts_count = 0

    for ticker, entries in summary_by_ticker.items():
        if len(entries) < 2:
            continue

        entries.sort(key=lambda x: x['sort_key'])
        latest = entries[-1]
        prior = entries[-2]

        if not latest['text'] or not prior['text']:
            continue

        # Count hedging and confidence in summaries
        latest_words = len(latest['text'].split())
        prior_words = len(prior['text'].split())
        if latest_words < 50 or prior_words < 50:
            continue

        latest_hedging = count_lexicon(latest['text'], HEDGING_WORDS)
        prior_hedging = count_lexicon(prior['text'], HEDGING_WORDS)
        latest_confidence = count_lexicon(latest['text'], CONFIDENCE_WORDS)
        prior_confidence = count_lexicon(prior['text'], CONFIDENCE_WORDS)

        # Normalize per 1000 words
        lh = round(latest_hedging / latest_words * 1000, 2)
        ph = round(prior_hedging / prior_words * 1000, 2)
        lc = round(latest_confidence / latest_words * 1000, 2)
        pc = round(prior_confidence / prior_words * 1000, 2)

        # Detect shifts
        hedging_change = round(((lh - ph) / ph * 100) if ph > 0 else (100 if lh > 0 else 0), 1)
        confidence_change = round(((lc - pc) / pc * 100) if pc > 0 else (-100 if pc > 0 else 0), 1)

        # Also check for new risk topics in transcript analysis
        new_topics = []
        ticker_rows = sorted(by_ticker.get(ticker, []),
                             key=lambda x: period_sort_key(x.get('quarter', ''), x.get('year', '')))
        if len(ticker_rows) >= 2:
            latest_row = ticker_rows[-1]
            prior_row = ticker_rows[-2]
            topic_keys = [k for k in latest_row.keys() if k.startswith('topic_')]
            for tk_col in topic_keys:
                latest_val = int(latest_row.get(tk_col, 0) or 0)
                prior_val = int(prior_row.get(tk_col, 0) or 0)
                if latest_val > 5 and prior_val == 0:
                    new_topics.append(tk_col.replace('topic_', '').replace('_', ' '))

        # Determine severity
        severity = 'none'
        descriptions = []

        if hedging_change > 50:
            severity = 'high'
            descriptions.append(f"Hedging language up {hedging_change:.0f}%")
        elif hedging_change > 25:
            if severity == 'none':
                severity = 'medium'
            descriptions.append(f"Hedging language up {hedging_change:.0f}%")

        if confidence_change < -40:
            severity = 'high'
            descriptions.append(f"Confidence language down {abs(confidence_change):.0f}%")
        elif confidence_change < -20:
            if severity == 'none':
                severity = 'medium'
            descriptions.append(f"Confidence language down {abs(confidence_change):.0f}%")

        if new_topics:
            if severity == 'none':
                severity = 'low'
            descriptions.append(f"New topics: {', '.join(new_topics)}")

        if severity != 'none':
            alerts_count += 1
            tone_shifts[ticker] = {
                'severity': severity,
                'latest_quarter': f"{latest['quarter']}_{latest['year']}",
                'prior_quarter': f"{prior['quarter']}_{prior['year']}",
                'hedging_per_1k_latest': lh,
                'hedging_per_1k_prior': ph,
                'hedging_change_pct': hedging_change,
                'confidence_per_1k_latest': lc,
                'confidence_per_1k_prior': pc,
                'confidence_change_pct': confidence_change,
                'new_risk_topics': new_topics,
                'description': '; '.join(descriptions),
            }

    print(f"      Found {alerts_count} tone shift alerts")
    return tone_shifts


# ═══════════════════════════════════════════════════════════════════════════════
# F3 — Analyst Question Clustering
# ═══════════════════════════════════════════════════════════════════════════════

def extract_analyst_questions(transcript_path):
    """Extract analyst question text from a raw transcript file."""
    with open(transcript_path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    questions = []
    current_role = None
    current_text = []
    speaker_pat = re.compile(r'\[([^\]]+?)\s*-\s*(Executives?|Analysts?|Operator)\]')

    for line in lines:
        match = speaker_pat.search(line)
        if match:
            # Save previous analyst block
            if current_role in ('Analysts', 'Analyst') and current_text:
                questions.append(' '.join(current_text))
            current_role = match.group(2).strip()
            current_text = []
        elif current_role in ('Analysts', 'Analyst') and line.strip():
            current_text.append(line.strip())

    # Don't forget last block
    if current_role in ('Analysts', 'Analyst') and current_text:
        questions.append(' '.join(current_text))

    return questions


def classify_question(text):
    """Classify an analyst question into themes."""
    text_lower = text.lower()
    themes = []
    for theme, keywords in ANALYST_THEMES.items():
        score = sum(text_lower.count(kw) for kw in keywords)
        if score >= 2:  # Need at least 2 keyword hits
            themes.append((theme, score))
    return themes


def find_best_earnings_season(transcript_data):
    """Find the quarter with the most reports (the most recent full season)."""
    quarter_counts = Counter()
    for row in transcript_data:
        q = row.get('quarter', '')
        y = row.get('year', '')
        if q and y:
            quarter_counts[f"{q}_{y}"] = quarter_counts.get(f"{q}_{y}", 0) + 1
    # Among recent quarters, pick the one with the most reports
    if not quarter_counts:
        return None
    # Sort by period descending, pick the first with 3+ companies (smaller universe than O&G)
    sorted_periods = sorted(quarter_counts.items(),
                            key=lambda x: period_sort_key(*x[0].split('_')),
                            reverse=True)
    for period, count in sorted_periods:
        if count >= 3:
            return period
    # If no quarter has 3+, just use the latest
    return sorted_periods[0][0] if sorted_periods else None


def build_analyst_themes(latest_quarter=None, transcript_data=None):
    """F3: Cluster analyst questions by theme across all companies."""
    print("  F3: Clustering analyst questions by theme...")

    # Use the most recent full earnings season for richer data
    season_quarter = latest_quarter
    if transcript_data:
        best = find_best_earnings_season(transcript_data)
        if best:
            season_quarter = best
            print(f"      Using earnings season: {season_quarter}")

    theme_counts = Counter()
    theme_companies = defaultdict(set)
    total_questions = 0

    # Iterate Companies/{Category}/{Company_Folder}/Transcripts/*.txt
    for category_dir in sorted(RESEARCH_DIR.iterdir()):
        if not category_dir.is_dir() or category_dir.name.startswith(('_', '.')) or category_dir.name == 'transcript_analysis':
            continue
        for company_dir in sorted(category_dir.iterdir()):
            if not company_dir.is_dir():
                continue
            # Extract ticker from folder name pattern "Company_Ticker" (last part after last underscore)
            parts = company_dir.name.rsplit('_', 1)
            ticker = parts[-1] if len(parts) >= 2 else company_dir.name
            transcript_dir = company_dir / "Transcripts"
            if not transcript_dir.is_dir():
                continue

            # Get transcript files
            files = sorted(transcript_dir.glob('*.txt'))
            if not files:
                continue

            if season_quarter:
                q, y = season_quarter.split('_')
                filtered = [f for f in files if f"_{q}_{y}_" in f.name or f"_{q}_{y}" in f.name]
                if filtered:
                    files = filtered
                else:
                    continue  # Skip companies without this quarter

            # Use latest transcript
            target = files[-1]
            questions = extract_analyst_questions(target)
            total_questions += len(questions)

            for q_text in questions:
                themes = classify_question(q_text)
                for theme, score in themes:
                    theme_counts[theme] += 1
                    theme_companies[theme].add(ticker)

    # Build sorted output
    result = []
    for theme, count in theme_counts.most_common():
        result.append({
            'theme': theme,
            'theme_label': theme.replace('_', ' ').title(),
            'count': count,
            'companies': sorted(theme_companies[theme]),
            'num_companies': len(theme_companies[theme]),
        })

    print(f"      Analyzed {total_questions} analyst questions, found {len(result)} themes")
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# F4 — Guidance vs Actuals / Credibility Tracker
# ═══════════════════════════════════════════════════════════════════════════════

def build_credibility(transcript_data, summaries):
    """F4: Track whether companies deliver on prior guidance."""
    print("  F4: Building credibility tracker...")

    # Group by ticker sorted by period
    by_ticker = defaultdict(list)
    for row in transcript_data:
        tk = row['ticker']
        q = row.get('quarter', '')
        y = row.get('year', '')
        if q and y:
            by_ticker[tk].append({
                'quarter': q,
                'year': y,
                'sort_key': period_sort_key(q, y),
                'guidance': row.get('guidance_direction', 'Not Detected'),
                'sentiment': float(row.get('sentiment_score', 0) or 0),
            })

    credibility = {}
    for ticker, entries in by_ticker.items():
        if len(entries) < 3:
            continue

        entries.sort(key=lambda x: x['sort_key'])
        history = []

        for i in range(1, len(entries)):
            prev = entries[i - 1]
            curr = entries[i]

            # Did the prior quarter's guidance hold?
            # If they raised guidance and sentiment improved or held -> delivered
            # If they raised guidance but sentiment dropped significantly -> missed
            prev_guidance = prev['guidance']
            curr_sentiment_delta = curr['sentiment'] - prev['sentiment']

            if prev_guidance == 'Raised':
                delivered = curr_sentiment_delta > -3  # Allow slight dips
            elif prev_guidance == 'Lowered':
                delivered = True  # Lowering expectations = easier to meet
            elif prev_guidance == 'Maintained':
                delivered = curr_sentiment_delta > -5  # Should be stable
            else:
                continue  # Skip if no guidance detected

            history.append({
                'quarter': f"{curr['quarter']}_{curr['year']}",
                'prior_guidance': prev_guidance,
                'sentiment_delta': round(curr_sentiment_delta, 2),
                'delivered': delivered,
            })

        if not history:
            continue

        # Score: percentage of quarters where guidance was met (last 8 quarters max)
        recent = history[-8:]
        score = round(sum(1 for h in recent if h['delivered']) / len(recent) * 100, 0)

        credibility[ticker] = {
            'score': int(score),
            'quarters_evaluated': len(recent),
            'history': recent[-4:],  # Keep last 4 for display
            'latest_delivered': recent[-1]['delivered'] if recent else None,
        }

    print(f"      Built credibility scores for {len(credibility)} companies")
    return credibility


# ═══════════════════════════════════════════════════════════════════════════════
# F7 — Comparative Earnings Timeline
# ═══════════════════════════════════════════════════════════════════════════════

def build_timeline(transcript_data, companies_meta, latest_quarter=None):
    """F7: Build ordered timeline of earnings reports with sentiment."""
    print("  F7: Building earnings timeline...")

    # Find latest quarter if not specified
    all_periods = set()
    for row in transcript_data:
        q = row.get('quarter', '')
        y = row.get('year', '')
        if q and y:
            all_periods.add((period_sort_key(q, y), q, y))

    if not all_periods:
        return []

    if latest_quarter:
        q_str, y_str = latest_quarter.split('_')
        target_key = period_sort_key(q_str, y_str)
    else:
        # Use the most recent full season, not necessarily the absolute latest
        best = find_best_earnings_season(transcript_data)
        if best:
            q_str, y_str = best.split('_')
            target_key = period_sort_key(q_str, y_str)
        else:
            target_key = max(all_periods, key=lambda x: x[0])[0]

    # Collect all entries for the target quarter
    entries = []
    for row in transcript_data:
        q = row.get('quarter', '')
        y = row.get('year', '')
        if period_sort_key(q, y) != target_key:
            continue

        ticker = row['ticker']
        meta = companies_meta.get(ticker, {})
        company_name = meta.get('company', '') or row.get('company', '') or ticker
        entries.append({
            'company': company_name,
            'ticker': ticker,
            'subsector': meta.get('subsector', row.get('subsector', 'Unknown')),
            'date': row.get('date', ''),
            'sentiment': round(float(row.get('sentiment_score', 0) or 0), 2),
            'guidance': row.get('guidance_direction', 'Not Detected'),
        })

    # Sort by date
    entries.sort(key=lambda x: x['date'])

    # Compute running average sentiment
    running_total = 0
    for i, entry in enumerate(entries):
        running_total += entry['sentiment']
        entry['running_avg_sentiment'] = round(running_total / (i + 1), 2)

    print(f"      Timeline: {len(entries)} reports for latest quarter")
    return entries


# ═══════════════════════════════════════════════════════════════════════════════
# F1 — Earnings Season Scorecard
# ═══════════════════════════════════════════════════════════════════════════════

def build_scorecard(transcript_data, summaries, extracted_metrics,
                    credibility, tone_shifts, companies_meta):
    """F1: Build cross-company earnings comparison table."""
    print("  F1: Building earnings season scorecard...")

    # Use most recent full earnings season (not the latest quarter which may only have 1 company)
    best_season = find_best_earnings_season(transcript_data)
    if best_season:
        latest_q, latest_y = best_season.split('_')
        latest_key = period_sort_key(latest_q, latest_y)
    else:
        # Fallback to absolute latest
        latest_key = 0
        latest_q = ''
        latest_y = ''
        for row in transcript_data:
            q = row.get('quarter', '')
            y = row.get('year', '')
            sk = period_sort_key(q, y)
            if sk > latest_key:
                latest_key = sk
                latest_q = q
                latest_y = y

    if not latest_q:
        return {}

    # Group transcript data by ticker for latest quarter
    latest_data = {}
    prior_data = {}
    prior_key = latest_key - 1  # Previous quarter
    if latest_q == 'Q1':
        prior_key = (int(latest_y) - 1) * 10 + 4

    for row in transcript_data:
        q = row.get('quarter', '')
        y = row.get('year', '')
        sk = period_sort_key(q, y)
        tk = row['ticker']

        if sk == latest_key:
            latest_data[tk] = row
        elif sk == prior_key:
            prior_data[tk] = row

    scorecard = {}
    for ticker, row in latest_data.items():
        meta = companies_meta.get(ticker, {})
        sentiment = float(row.get('sentiment_score', 0) or 0)
        prior = prior_data.get(ticker, {})
        prior_sentiment = float(prior.get('sentiment_score', 0) or 0) if prior else 0

        # Get extracted metrics for this company/quarter
        summary_key = f"{ticker}_{latest_q}_{latest_y}"
        metrics = extracted_metrics.get(summary_key, {})

        company_name = meta.get('company', '') or row.get('company', '') or ticker

        sc = {
            'company': company_name,
            'subsector': meta.get('subsector', '') or row.get('subsector', 'Unknown'),
            'quarter': f"{latest_q}_{latest_y}",
            'sentiment': round(sentiment, 2),
            'sentiment_prior': round(prior_sentiment, 2),
            'sentiment_delta': round(sentiment - prior_sentiment, 2),
            'guidance': row.get('guidance_direction', 'Not Detected'),
            'credibility_score': credibility.get(ticker, {}).get('score', None),
            'tone_shift_severity': tone_shifts.get(ticker, {}).get('severity', 'none'),
        }
        sc.update(metrics)
        scorecard[ticker] = sc

    print(f"      Scorecard: {len(scorecard)} companies for {latest_q} {latest_y}")
    return scorecard


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='Build transcript intelligence bundle')
    parser.add_argument('--quarter', type=str, default=None,
                        help='Target quarter (e.g., Q4_2025). Default: latest available.')
    args = parser.parse_args()

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Transcript Intelligence Engine starting...")

    # Load data
    summaries = load_summaries()
    transcript_data = load_transcript_csv()
    companies_meta = load_companies()
    print(f"  Loaded: {len(summaries)} summaries, {len(transcript_data)} transcript rows, "
          f"{len(companies_meta)} companies")

    # Normalize alias tickers in summaries (e.g., BVRDF_Q4_2025 → BVI_Q4_2025)
    normalized = {}
    for key, val in summaries.items():
        parts = key.split('_', 1)
        tk = parts[0]
        rest = parts[1] if len(parts) > 1 else ''
        canonical = NDT_TICKER_ALIASES.get(tk, tk)
        if canonical is None:
            continue  # Skip non-universe aliases like SGSOF
        new_key = f"{canonical}_{rest}" if rest else canonical
        if new_key not in normalized:  # don't overwrite if canonical already present
            normalized[new_key] = val
    summaries = normalized
    print(f"  After alias normalization: {len(summaries)} summaries")

    # Normalize alias tickers in transcript CSV rows
    for row in transcript_data:
        tk = row.get('ticker', '')
        canonical = NDT_TICKER_ALIASES.get(tk, tk)
        if canonical:
            row['ticker'] = canonical

    if not summaries and not transcript_data:
        print("  ERROR: No transcript data found. Run analyze_transcripts.py and summarize_transcripts.py first.")
        return

    # Determine latest quarter (from NDT universe tickers only)
    latest_quarter = args.quarter
    if not latest_quarter and transcript_data:
        best_key = 0
        best_q = ''
        best_y = ''
        for row in transcript_data:
            tk = row.get('ticker', '')
            if tk not in NDT_UNIVERSE:
                continue  # Only consider NDT universe tickers for latest quarter
            q = row.get('quarter', '')
            y = row.get('year', '')
            sk = period_sort_key(q, y)
            if sk > best_key:
                best_key = sk
                best_q = q
                best_y = y
        if best_q:
            latest_quarter = f"{best_q}_{best_y}"
    print(f"  Target quarter: {latest_quarter or 'auto-detect'}")

    # Build all features
    extracted_metrics = build_extracted_metrics(summaries)
    tone_shifts = build_tone_shifts(summaries, transcript_data)
    analyst_themes = build_analyst_themes(latest_quarter, transcript_data)
    credibility = build_credibility(transcript_data, summaries)
    timeline = build_timeline(transcript_data, companies_meta, latest_quarter)
    scorecard = build_scorecard(transcript_data, summaries, extracted_metrics,
                                credibility, tone_shifts, companies_meta)

    # Filter all outputs to NDT universe tickers only
    def is_ndt_ticker(tk):
        """Check if ticker belongs to NDT universe (including aliases)."""
        if tk in NDT_UNIVERSE:
            return True
        alias = NDT_TICKER_ALIASES.get(tk)
        return alias is not None and alias in NDT_UNIVERSE

    def filter_dict(d):
        """Filter dict keys to NDT universe tickers, normalizing aliases."""
        result = {}
        for tk, val in d.items():
            if tk in NDT_UNIVERSE:
                result[tk] = val
            elif tk in NDT_TICKER_ALIASES and NDT_TICKER_ALIASES[tk] in NDT_UNIVERSE:
                # Remap alias to canonical ticker
                canonical = NDT_TICKER_ALIASES[tk]
                if canonical not in result:  # don't overwrite if canonical already present
                    result[canonical] = val
        return result

    scorecard = filter_dict(scorecard)
    tone_shifts = filter_dict(tone_shifts)
    credibility = filter_dict(credibility)
    extracted_metrics = {k: v for k, v in extracted_metrics.items()
                         if k.split('_')[0] in NDT_UNIVERSE or
                         NDT_TICKER_ALIASES.get(k.split('_')[0], '') in NDT_UNIVERSE}
    timeline = [e for e in timeline if is_ndt_ticker(e.get('ticker', ''))]
    # Remap timeline ticker aliases
    for e in timeline:
        tk = e.get('ticker', '')
        if tk in NDT_TICKER_ALIASES and NDT_TICKER_ALIASES[tk]:
            e['ticker'] = NDT_TICKER_ALIASES[tk]
    # Filter analyst themes companies list
    for theme in analyst_themes:
        theme['companies'] = [c for c in theme.get('companies', []) if is_ndt_ticker(c)]
        theme['num_companies'] = len(theme['companies'])
    analyst_themes = [t for t in analyst_themes if t['num_companies'] > 0]

    filtered_counts = f"Scorecard: {len(scorecard)}, Credibility: {len(credibility)}, " \
                      f"Tone shifts: {len(tone_shifts)}, Timeline: {len(timeline)}"
    print(f"  After NDT universe filter: {filtered_counts}")

    # Assemble output
    output = {
        'generated_at': datetime.now().isoformat(),
        'latest_quarter': latest_quarter,
        'scorecard': scorecard,
        'tone_shifts': tone_shifts,
        'analyst_themes': analyst_themes,
        'credibility': credibility,
        'extracted_metrics': extracted_metrics,
        'timeline': timeline,
    }

    # Save
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    size_kb = OUTPUT_FILE.stat().st_size / 1024
    print(f"\n  Output: {OUTPUT_FILE}")
    print(f"  Size: {size_kb:.0f} KB")
    print(f"\n  Scorecard: {len(scorecard)} companies")
    print(f"  Tone shifts: {len(tone_shifts)} alerts")
    print(f"  Analyst themes: {len(analyst_themes)} themes")
    print(f"  Credibility: {len(credibility)} companies scored")
    print(f"  Metrics extracted: {len(extracted_metrics)} summaries")
    print(f"  Timeline: {len(timeline)} reports")
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Done.")


if __name__ == '__main__':
    main()
