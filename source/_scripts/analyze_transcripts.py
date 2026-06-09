#!/usr/bin/env python3
"""
NDT Earnings Transcript Analyzer
==================================
Scans all earnings call transcripts across the NDT universe, extracts:
  - Management sentiment (positive/negative word frequency, NDT-tuned lexicon)
  - Key topic detection (10 NDT-specific categories)
  - Guidance language (raised, lowered, maintained, reiterated)
  - Speaker breakdown (exec vs analyst question analysis)
  - Quarter-over-quarter trend tracking

Output:
  - Companies/transcript_analysis/{ticker}_transcript_analysis.csv  (per-company)
  - Companies/transcript_analysis/transcript_summary.csv            (all companies)
  - Companies/transcript_analysis/guidance_tracker.csv              (guidance changes)
  - Companies/transcript_analysis/topic_trends.csv                  (topic frequency over time)
  - Companies/transcript_analysis/sentiment_trends.csv              (sentiment by quarter)
  - Companies/transcript_analysis/analysis_bundle.json              (dashboard injection)

Usage: python3 analyze_transcripts.py [--recent N]  (N = days, default all)

Modeled after Oil_Gas_Intel's analyze_transcripts.py, adapted for NDT/TIC industry.
"""

import os, re, json, csv, sys, argparse
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter, defaultdict

BASE_DIR = Path(__file__).resolve().parent.parent  # Inspection_Intel/
RESEARCH_DIR = BASE_DIR / "Companies"
OUTPUT_DIR = BASE_DIR / "Industry_Data" / "Transcript_Analysis"
LOG_DIR = BASE_DIR / "_scripts" / "logs"

# ─── Category Mappings ───
# Maps folder category names to display categories
CATEGORY_MAP = {
    'NDT_Services': 'NDT Services',
    'Global_NDT': 'Global NDT',
    'NDT_Adjacent': 'NDT Adjacent',
    'Flow_Control': 'Flow Control',
    'Mech_OnSite_Services': 'Mech. & On-Site Services',
    'SmallCap_NDT': 'SmallCap NDT',
    'TIC_Majors': 'TIC Majors',
    'Industrial_Inspection': 'Industrial Inspection',
}

# ─── Sentiment Lexicon (domain-tuned for NDT/TIC/inspection earnings calls) ───
POSITIVE_WORDS = {
    # General positive
    'growth', 'increase', 'increased', 'increasing', 'improvement', 'improved',
    'strong', 'stronger', 'record', 'exceeded', 'outperformed', 'beat',
    'ahead', 'positive', 'opportunity', 'opportunities', 'upside', 'momentum',
    'accelerate', 'accelerated', 'robust', 'solid', 'excellent', 'exceptional',
    'raised', 'upgraded', 'higher', 'optimize', 'optimized', 'efficient',
    'profitability', 'profitable', 'accretive', 'synergies', 'milestone',
    'expanded', 'expanding', 'outpaced', 'surpassed', 'strengthened',
    # NDT/TIC-specific positive
    'backlog', 'utilization', 'certification', 'accreditation', 'compliance',
    'recurring', 'integrated', 'diversified', 'scalable', 'proprietary',
    'win', 'wins', 'awarded', 'renewal', 'renewals', 'retention',
    'turnaround', 'outage', 'shutdown', 'uptime', 'safety',
    'digitization', 'automation', 'innovation', 'advanced',
    'leverage', 'margin', 'margins', 'deleveraging', 'deleverage',
}

NEGATIVE_WORDS = {
    # General negative
    'decline', 'declined', 'declining', 'decrease', 'decreased', 'lower',
    'lowered', 'weak', 'weaker', 'weakness', 'miss', 'missed', 'below',
    'challenging', 'challenges', 'headwind', 'headwinds', 'risk', 'risks',
    'uncertainty', 'uncertain', 'volatile', 'volatility', 'downturn',
    'impairment', 'writedown', 'loss', 'losses', 'negative', 'deteriorate',
    'deteriorated', 'slowdown', 'slowing', 'reduced', 'reduction', 'pressure',
    'pressured', 'cut', 'curtail', 'curtailed', 'suspended', 'deferred',
    'constraint', 'constraints', 'disruption', 'disrupted',
    # NDT/TIC-specific negative
    'delay', 'delays', 'delayed', 'cancellation', 'cancelled',
    'underutilized', 'overcapacity', 'attrition', 'turnover',
    'litigation', 'liability', 'penalty', 'penalties',
    'pricing', 'commoditized', 'competitive', 'underbid',
    'restructuring', 'closure', 'closures', 'shutdown',
    'weather', 'hurricane', 'storm', 'flooding',
}

# ─── Topic Keywords (10 NDT-specific categories) ───
TOPICS = {
    'backlog_pipeline': [
        'backlog', 'pipeline', 'book-to-bill', 'book to bill', 'bookings',
        'order', 'orders', 'awarded', 'contract win', 'contract wins',
        'new business', 'proposal', 'proposals', 'bid', 'bids',
        'master service agreement', 'msa', 'long-term contract', 'multi-year',
    ],
    'nuclear': [
        'nuclear', 'reactor', 'nuclear power', 'nrc', 'nuclear regulatory',
        'decommissioning', 'outage', 'refueling', 'plant life extension',
        'nuclear new build', 'small modular reactor', 'smr', 'radiation',
        'radiography', 'isotope', 'nuclear waste', 'spent fuel',
    ],
    'aerospace_defense': [
        'aerospace', 'defense', 'defence', 'aviation', 'aircraft',
        'airframe', 'engine', 'oem', 'mro', 'pratt', 'ge aerospace',
        'boeing', 'airbus', 'faa', 'easa', 'nadcap', 'as9100',
        'composite', 'composites', 'additive', 'space', 'satellite',
        'rocket', 'defense budget', 'military', 'naval', 'shipbuilding',
    ],
    'infrastructure': [
        'infrastructure', 'bridge', 'bridges', 'pipeline', 'pipelines',
        'transmission', 'power grid', 'rail', 'railroad', 'highway',
        'dam', 'tunnel', 'construction', 'iija', 'infrastructure bill',
        'water', 'wastewater', 'utility', 'utilities', 'data center',
        'building inspection', 'structural', 'concrete',
    ],
    'digital_automation': [
        'digital', 'digitization', 'digitalization', 'automation', 'automated',
        'artificial intelligence', 'ai', 'machine learning', 'ml',
        'drone', 'drones', 'uav', 'robot', 'robotic', 'robotics',
        'software', 'saas', 'platform', 'cloud', 'data analytics',
        'sensor', 'sensors', 'iot', 'remote monitoring', 'digital twin',
        'phased array', 'paut', 'tofd', 'computed radiography',
    ],
    'mergers_acquisitions': [
        'acquisition', 'acquisitions', 'acquire', 'acquired', 'merger',
        'takeover', 'bolt-on', 'bolt on', 'purchase', 'consolidation',
        'deal', 'transaction', 'integration', 'synergies', 'tuck-in',
        'divestiture', 'divestment', 'divest', 'spin-off', 'carve-out',
    ],
    'margins_profitability': [
        'margin', 'margins', 'gross margin', 'operating margin', 'ebitda margin',
        'profitability', 'gross profit', 'operating income', 'ebitda',
        'cost reduction', 'cost savings', 'efficiency', 'productivity',
        'operating leverage', 'price increase', 'pricing power',
        'sg&a', 'overhead', 'restructuring', 'lean', 'continuous improvement',
    ],
    'regulation_compliance': [
        'regulation', 'regulatory', 'compliance', 'code', 'codes',
        'api', 'asme', 'astm', 'iso', 'nace', 'aws', 'osha',
        'safety standard', 'safety standards', 'certification', 'accreditation',
        'audit', 'audits', 'inspection mandate', 'mandatory inspection',
        'environmental', 'esg', 'sustainability', 'carbon', 'emissions',
        'corrosion', 'integrity management', 'asset integrity',
    ],
    'international_expansion': [
        'international', 'global', 'europe', 'european', 'asia', 'asian',
        'middle east', 'latin america', 'canada', 'canadian', 'uk',
        'france', 'germany', 'australia', 'india', 'china', 'japan',
        'offshore', 'overseas', 'cross-border', 'foreign exchange', 'fx',
        'geographic expansion', 'new market', 'new markets',
    ],
    'capital_allocation': [
        'capital allocation', 'capex', 'capital expenditure', 'capital spending',
        'dividend', 'buyback', 'share repurchase', 'return to shareholders',
        'debt', 'leverage', 'deleverage', 'deleveraging', 'credit facility',
        'revolver', 'refinance', 'net debt', 'debt reduction', 'balance sheet',
        'free cash flow', 'cash flow', 'working capital', 'cash conversion',
    ],
}

# ─── Guidance Detection ───
GUIDANCE_RAISED = [
    'raised', 'increased guidance', 'lifted', 'upgraded', 'boosted',
    'higher guidance', 'above the high end', 'raised our',
    'increasing our guidance', 'revised upward', 'raising guidance',
    'raising our', 'increased our guidance',
]
GUIDANCE_LOWERED = [
    'lowered', 'reduced guidance', 'cut guidance', 'decreased guidance',
    'revised down', 'below the low end', 'revised downward',
    'lower guidance', 'trimmed', 'revised lower',
    'lowering our', 'reducing our guidance',
]
GUIDANCE_MAINTAINED = [
    'maintained', 'reiterated', 'reaffirmed', 'unchanged',
    'on track', 'confirmed', 'in line with', 'consistent with',
    'narrowing our', 'tightening our', 'affirming',
]


def parse_transcript(filepath):
    """Parse an earnings call transcript into structured data."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()

    result = {
        'file': filepath.name,
        'quarter': '',
        'year': '',
        'date': '',
        'full_text': text,
        'speakers': [],
    }

    # Extract metadata from header
    lines = text.split('\n')
    for line in lines[:10]:
        # Quarter/Year from header
        qm = re.search(r'Q([1-4])\s*(\d{4})', line)
        if qm:
            result['quarter'] = f"Q{qm.group(1)}"
            result['year'] = qm.group(2)
        # Date — handle ISO datetime (2025-11-05T14:00:00Z) or plain date
        dm = re.search(r'Date:\s*(\d{4}-\d{2}-\d{2})', line)
        if dm:
            result['date'] = dm.group(1)

    # Fallback: try filename
    if not result['quarter']:
        qm = re.search(r'Q([1-4])_(\d{4})', filepath.name)
        if qm:
            result['quarter'] = f"Q{qm.group(1)}"
            result['year'] = qm.group(2)

    if not result['date']:
        dm = re.search(r'(\d{4}-\d{2}-\d{2})', filepath.name)
        if dm:
            result['date'] = dm.group(1)

    # Parse speakers — format: [Speaker Name - Role]
    speaker_pattern = re.compile(r'\[([^\]]+?)\s*-\s*(Executives?|Analysts?|Operator)\]')
    current_speaker = None
    current_role = None
    current_text = []

    for line in lines:
        sm = speaker_pattern.search(line)
        if sm:
            if current_speaker and current_text:
                result['speakers'].append({
                    'name': current_speaker,
                    'role': current_role,
                    'text': ' '.join(current_text),
                })
            current_speaker = sm.group(1).strip()
            current_role = sm.group(2).strip()
            current_text = []
        elif current_speaker and line.strip():
            current_text.append(line.strip())

    if current_speaker and current_text:
        result['speakers'].append({
            'name': current_speaker,
            'role': current_role,
            'text': ' '.join(current_text),
        })

    return result


def analyze_sentiment(text):
    """Score sentiment using NDT-tuned domain lexicon."""
    words = re.findall(r'\b[a-z]+\b', text.lower())
    word_count = len(words) if words else 1
    pos = sum(1 for w in words if w in POSITIVE_WORDS)
    neg = sum(1 for w in words if w in NEGATIVE_WORDS)
    # Normalized per 1000 words
    return {
        'positive_count': pos,
        'negative_count': neg,
        'sentiment_score': round((pos - neg) / word_count * 1000, 2),
        'positive_per_1k': round(pos / word_count * 1000, 2),
        'negative_per_1k': round(neg / word_count * 1000, 2),
        'word_count': word_count,
    }


def detect_topics(text):
    """Count topic mentions across 10 NDT-specific categories."""
    text_lower = text.lower()
    topic_counts = {}
    for topic, keywords in TOPICS.items():
        count = sum(text_lower.count(kw) for kw in keywords)
        topic_counts[topic] = count
    return topic_counts


def detect_guidance(text):
    """Detect guidance language direction from executive commentary."""
    text_lower = text.lower()
    raised = sum(text_lower.count(g) for g in GUIDANCE_RAISED)
    lowered = sum(text_lower.count(g) for g in GUIDANCE_LOWERED)
    maintained = sum(text_lower.count(g) for g in GUIDANCE_MAINTAINED)

    if raised > lowered and raised > 0:
        direction = 'Raised'
    elif lowered > raised and lowered > 0:
        direction = 'Lowered'
    elif maintained > 0:
        direction = 'Maintained'
    else:
        direction = 'Not Detected'

    return {
        'guidance_direction': direction,
        'guidance_raised_signals': raised,
        'guidance_lowered_signals': lowered,
        'guidance_maintained_signals': maintained,
    }


def analyze_company(transcript_dir, ticker, company_name, category):
    """Analyze all transcripts for a single company."""
    if not transcript_dir.is_dir():
        return []

    # Collect all transcript files (.txt only, >100 bytes)
    files = sorted([f for f in transcript_dir.iterdir()
                    if f.suffix == '.txt' and f.stat().st_size > 100])
    if not files:
        return []

    results = []
    for tf in files:
        parsed = parse_transcript(tf)
        text = parsed['full_text']

        # Exec-only text (for sentiment — exclude analyst questions)
        exec_text = ' '.join(s['text'] for s in parsed['speakers']
                            if s['role'] in ('Executives', 'Executive'))
        analyst_text = ' '.join(s['text'] for s in parsed['speakers']
                               if s['role'] in ('Analysts', 'Analyst'))

        sentiment = analyze_sentiment(exec_text if exec_text else text)
        topics = detect_topics(text)  # Topics from full text
        guidance = detect_guidance(exec_text if exec_text else text)

        exec_names = list(set(s['name'] for s in parsed['speakers']
                              if s['role'] in ('Executives', 'Executive')))
        analyst_names = list(set(s['name'] for s in parsed['speakers']
                                if s['role'] in ('Analysts', 'Analyst')))

        row = {
            'ticker': ticker,
            'company': company_name,
            'category': category,
            'file': tf.name,
            'quarter': parsed['quarter'],
            'year': parsed['year'],
            'date': parsed['date'],
            'word_count': sentiment['word_count'],
            'sentiment_score': sentiment['sentiment_score'],
            'positive_per_1k': sentiment['positive_per_1k'],
            'negative_per_1k': sentiment['negative_per_1k'],
            'num_executives': len(exec_names),
            'num_analysts': len(analyst_names),
            'executives': '; '.join(exec_names[:5]),
            'analysts': '; '.join(analyst_names[:10]),
        }
        row.update({f'topic_{k}': v for k, v in topics.items()})
        row.update(guidance)
        results.append(row)

    return results


def discover_companies():
    """Auto-discover companies by scanning Companies directory structure."""
    companies = []
    if not RESEARCH_DIR.exists():
        return companies

    for category_dir in sorted(RESEARCH_DIR.iterdir()):
        if not category_dir.is_dir() or category_dir.name.startswith(('.', '_')):
            continue
        if category_dir.name == 'transcript_analysis':
            continue

        category_name = CATEGORY_MAP.get(category_dir.name, category_dir.name)

        for company_dir in sorted(category_dir.iterdir()):
            if not company_dir.is_dir():
                continue
            # Extract ticker from folder name (e.g., MistrasGroup_MG -> MG)
            parts = company_dir.name.rsplit('_', 1)
            if len(parts) == 2:
                company_display = parts[0]
                ticker = parts[1]
            else:
                continue

            transcript_dir = company_dir / 'Transcripts'
            if transcript_dir.exists():
                companies.append({
                    'ticker': ticker,
                    'company': company_display,
                    'category': category_name,
                    'transcript_dir': transcript_dir,
                })

    return companies


def build_dashboard_bundle(all_results):
    """Build a JSON bundle for dashboard injection with charts/tables data."""
    bundle = {
        'generated_at': datetime.now().isoformat(),
        'total_transcripts': len(all_results),
        'companies': {},
        'sentiment_trends': {},
        'topic_trends': {},
        'guidance_summary': {},
        'category_sentiment': {},
        'latest_sentiment': {},
    }

    # Group by ticker
    by_ticker = defaultdict(list)
    for r in all_results:
        by_ticker[r['ticker']].append(r)

    # Per-company summary
    for ticker, rows in by_ticker.items():
        rows_sorted = sorted(rows, key=lambda x: (x.get('year', ''), x.get('quarter', '')))
        latest = rows_sorted[-1] if rows_sorted else None

        sentiment_history = [{
            'period': f"{r['year']}-{r['quarter']}",
            'score': r['sentiment_score'],
            'positive': r['positive_per_1k'],
            'negative': r['negative_per_1k'],
        } for r in rows_sorted]

        topic_history = [{
            'period': f"{r['year']}-{r['quarter']}",
            **{k: r.get(f'topic_{k}', 0) for k in TOPICS}
        } for r in rows_sorted]

        guidance_history = [{
            'period': f"{r['year']}-{r['quarter']}",
            'direction': r['guidance_direction'],
        } for r in rows_sorted]

        avg_sentiment = sum(r['sentiment_score'] for r in rows) / len(rows)

        bundle['companies'][ticker] = {
            'company': latest['company'] if latest else '',
            'category': latest['category'] if latest else '',
            'transcript_count': len(rows),
            'avg_sentiment': round(avg_sentiment, 2),
            'latest_sentiment': latest['sentiment_score'] if latest else 0,
            'latest_guidance': latest['guidance_direction'] if latest else 'N/A',
            'sentiment_history': sentiment_history,
            'topic_history': topic_history,
            'guidance_history': guidance_history,
        }

        # Latest sentiment for dashboard ranking
        if latest:
            bundle['latest_sentiment'][ticker] = {
                'company': latest['company'],
                'category': latest['category'],
                'score': latest['sentiment_score'],
                'period': f"{latest['year']}-{latest['quarter']}",
                'direction': latest['guidance_direction'],
            }

    # Sentiment trends (aggregated by quarter)
    period_sentiments = defaultdict(list)
    for r in all_results:
        period = f"{r['year']}-{r['quarter']}" if r['year'] and r['quarter'] else None
        if period:
            period_sentiments[period].append(r['sentiment_score'])

    for period in sorted(period_sentiments.keys()):
        vals = period_sentiments[period]
        bundle['sentiment_trends'][period] = {
            'avg': round(sum(vals) / len(vals), 2),
            'min': round(min(vals), 2),
            'max': round(max(vals), 2),
            'count': len(vals),
        }

    # Topic trends (aggregated by quarter)
    topic_agg = defaultdict(lambda: defaultdict(int))
    for r in all_results:
        period = f"{r['year']}-{r['quarter']}" if r['year'] and r['quarter'] else None
        if period:
            for topic in TOPICS:
                topic_agg[period][topic] += r.get(f'topic_{topic}', 0)

    for period in sorted(topic_agg.keys()):
        bundle['topic_trends'][period] = dict(topic_agg[period])

    # Guidance summary (overall counts)
    guidance_counts = Counter(r['guidance_direction'] for r in all_results)
    bundle['guidance_summary'] = dict(guidance_counts)

    # Category-level sentiment
    cat_sentiments = defaultdict(list)
    for r in all_results:
        cat_sentiments[r.get('category', 'Unknown')].append(r['sentiment_score'])
    for cat, vals in cat_sentiments.items():
        bundle['category_sentiment'][cat] = {
            'avg': round(sum(vals) / len(vals), 2),
            'count': len(vals),
        }

    return bundle


def main():
    parser = argparse.ArgumentParser(description='NDT Earnings Transcript Analyzer')
    parser.add_argument('--recent', type=int, default=0,
                        help='Only analyze transcripts from last N days')
    parser.add_argument('--ticker', type=str, default='',
                        help='Only analyze a specific ticker')
    parser.add_argument('--json-only', action='store_true',
                        help='Only output the JSON bundle (skip CSVs)')
    args = parser.parse_args()

    print(f"[{datetime.now()}] Starting NDT transcript analysis...")

    companies = discover_companies()
    print(f"  Discovered {len(companies)} companies with transcripts")

    if args.ticker:
        companies = [c for c in companies if c['ticker'].upper() == args.ticker.upper()]
        print(f"  Filtered to ticker: {args.ticker} ({len(companies)} found)")

    all_results = []
    companies_processed = 0
    transcripts_analyzed = 0

    for company in companies:
        ticker = company['ticker']
        company_name = company['company']
        category = company['category']
        transcript_dir = company['transcript_dir']

        results = analyze_company(transcript_dir, ticker, company_name, category)
        if results:
            companies_processed += 1
            transcripts_analyzed += len(results)
            all_results.extend(results)

            if not args.json_only:
                # Save per-company CSV
                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                company_csv = OUTPUT_DIR / f"{ticker}_transcript_analysis.csv"
                fieldnames = list(results[0].keys())
                with open(company_csv, 'w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(results)

    if not all_results:
        print("  No transcripts found to analyze.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not args.json_only:
        # ─── Output 1: Master summary CSV ───
        summary_csv = OUTPUT_DIR / "transcript_summary.csv"
        fieldnames = list(all_results[0].keys())
        with open(summary_csv, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(sorted(all_results,
                                    key=lambda x: (x['ticker'], x.get('date', ''))))
        print(f"  Saved: {summary_csv}")

        # ─── Output 2: Guidance tracker CSV ───
        guidance_rows = [r for r in all_results if r['guidance_direction'] != 'Not Detected']
        if guidance_rows:
            guidance_csv = OUTPUT_DIR / "guidance_tracker.csv"
            gf = ['ticker', 'company', 'category', 'quarter', 'year', 'date',
                  'guidance_direction', 'guidance_raised_signals',
                  'guidance_lowered_signals', 'guidance_maintained_signals',
                  'sentiment_score']
            with open(guidance_csv, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=gf)
                writer.writeheader()
                for r in sorted(guidance_rows,
                                key=lambda x: (x.get('date', ''), x['ticker'])):
                    writer.writerow({k: r.get(k, '') for k in gf})
            print(f"  Saved: {guidance_csv}")

        # ─── Output 3: Topic trends CSV ───
        topic_agg = defaultdict(lambda: defaultdict(int))
        for r in all_results:
            period = f"{r['year']}-{r['quarter']}" if r['year'] and r['quarter'] else 'Unknown'
            for topic in TOPICS:
                topic_agg[period][topic] += r.get(f'topic_{topic}', 0)

        topics_csv = OUTPUT_DIR / "topic_trends.csv"
        topic_names = sorted(TOPICS.keys())
        with open(topics_csv, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['period'] + topic_names)
            for period in sorted(topic_agg.keys()):
                row = [period] + [topic_agg[period].get(t, 0) for t in topic_names]
                writer.writerow(row)
        print(f"  Saved: {topics_csv}")

        # ─── Output 4: Sentiment trends CSV ───
        sentiment_agg = defaultdict(list)
        for r in all_results:
            period = f"{r['year']}-{r['quarter']}" if r['year'] and r['quarter'] else 'Unknown'
            sentiment_agg[period].append(r['sentiment_score'])

        sentiment_csv = OUTPUT_DIR / "sentiment_trends.csv"
        with open(sentiment_csv, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['period', 'avg_sentiment', 'min_sentiment',
                            'max_sentiment', 'transcript_count'])
            for period in sorted(sentiment_agg.keys()):
                vals = sentiment_agg[period]
                writer.writerow([
                    period,
                    round(sum(vals) / len(vals), 2),
                    round(min(vals), 2),
                    round(max(vals), 2),
                    len(vals),
                ])
        print(f"  Saved: {sentiment_csv}")

    # ─── Output 5: Dashboard JSON bundle ───
    bundle = build_dashboard_bundle(all_results)
    bundle_path = OUTPUT_DIR / "analysis_bundle.json"
    with open(bundle_path, 'w') as f:
        json.dump(bundle, f, indent=2)
    print(f"  Saved: {bundle_path}")

    # ─── Print summary ───
    print(f"\n  Companies analyzed: {companies_processed}")
    print(f"  Transcripts analyzed: {transcripts_analyzed}")

    # Guidance summary
    guidance_counts = Counter(r['guidance_direction'] for r in all_results)
    print(f"\n  Guidance signals across all transcripts:")
    for direction, count in guidance_counts.most_common():
        print(f"    {direction}: {count}")

    # Avg sentiment by category
    cat_sentiments = defaultdict(list)
    for r in all_results:
        cat_sentiments[r.get('category', 'Unknown')].append(r['sentiment_score'])
    print(f"\n  Avg sentiment by category:")
    for cat in sorted(cat_sentiments.keys()):
        vals = cat_sentiments[cat]
        avg = sum(vals) / len(vals)
        print(f"    {cat}: {avg:.1f} ({len(vals)} transcripts)")

    # Top 5 most positive / most negative latest transcripts
    latest_by_ticker = {}
    for r in sorted(all_results, key=lambda x: (x.get('year', ''), x.get('quarter', ''))):
        latest_by_ticker[r['ticker']] = r

    if latest_by_ticker:
        sorted_latest = sorted(latest_by_ticker.values(),
                               key=lambda x: x['sentiment_score'], reverse=True)
        print(f"\n  Sentiment Leaders (latest quarter):")
        for r in sorted_latest[:5]:
            print(f"    {r['ticker']:8s} {r['sentiment_score']:+6.1f}  ({r['quarter']} {r['year']})")
        print(f"\n  Sentiment Laggards (latest quarter):")
        for r in sorted_latest[-5:]:
            print(f"    {r['ticker']:8s} {r['sentiment_score']:+6.1f}  ({r['quarter']} {r['year']})")

    print(f"\n[{datetime.now()}] NDT transcript analysis complete.")


if __name__ == '__main__':
    main()
