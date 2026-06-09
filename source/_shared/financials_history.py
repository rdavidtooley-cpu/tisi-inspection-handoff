"""
Shared helpers for extracting historical financials from yfinance and
structuring them for the equities dashboard period selector UI.

Each refresh script imports and calls `fetch_historical_financials(tickers, logger)`
and injects the result into its equities HTML as `FINANCIALS_HISTORY`.

Output shape per ticker:
    {
      "quarterly":              [{period, fiscal_date, revenue, ebitda, net_income, interest_expense, ...}, ...],
      "annual":                 [{period, fiscal_date, ...same keys}, ...],
      "balance_sheet_quarterly": [{period, fiscal_date, total_debt, cash, stockholders_equity, ...}, ...],
      "balance_sheet_annual":    [{period, fiscal_date, ...same keys}, ...],
      "cashflow_quarterly":      [{period, fiscal_date, operating_cash_flow, capex, free_cash_flow}, ...],
      "cashflow_annual":         [{period, fiscal_date, ...same keys}, ...],
    }

Values are RAW DOLLARS (not pre-scaled). The dashboard UI auto-scales to millions.

Periods limited to the 5 most recent entries in each category (yfinance rarely
returns more than this reliably).
"""

from __future__ import annotations

import time
from typing import Dict, List, Any

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None


# --- Income statement field mapping (yfinance index label -> our snake_case key) ---
INCOME_FIELDS = {
    "Total Revenue": "revenue",
    "Cost Of Revenue": "cost_of_revenue",
    "Gross Profit": "gross_profit",
    "Operating Income": "operating_income",
    "EBITDA": "ebitda",
    "Net Income": "net_income",
    "Interest Expense": "interest_expense",
    "Basic EPS": "eps_basic",
    "Diluted EPS": "eps_diluted",
}

BALANCE_SHEET_FIELDS = {
    "Total Assets": "total_assets",
    "Total Liabilities Net Minority Interest": "total_liabilities",
    "Stockholders Equity": "stockholders_equity",
    "Total Debt": "total_debt",
    "Cash And Cash Equivalents": "cash",
    "Current Assets": "current_assets",
    "Current Liabilities": "current_liabilities",
    "Accounts Receivable": "accounts_receivable",
    "Accounts Payable": "accounts_payable",
}

CASHFLOW_FIELDS = {
    "Operating Cash Flow": "operating_cash_flow",
    "Capital Expenditure": "capex",
    "Free Cash Flow": "free_cash_flow",
    "Depreciation And Amortization": "depreciation_amortization",
}


def _period_key(col, period_fmt: str) -> str:
    """Build a period label from a DataFrame column (pandas Timestamp)."""
    if period_fmt == "year":
        return col.strftime("%Y")
    q = (col.month - 1) // 3 + 1
    return f"{col.strftime('%Y')}-Q{q}"


def _records_from_df(df, field_map: Dict[str, str], period_fmt: str) -> List[Dict[str, Any]]:
    """Generic: turn a yfinance financials DataFrame into a list of period records."""
    if df is None or df.empty:
        return []
    out: List[Dict[str, Any]] = []
    for col in df.columns:
        rec: Dict[str, Any] = {
            "period": _period_key(col, period_fmt),
            "fiscal_date": col.strftime("%Y-%m-%d"),
        }
        for src_label, key in field_map.items():
            if src_label in df.index:
                val = df.loc[src_label, col]
                try:
                    v = float(val)
                    rec[key] = v if v == v else None  # filter NaN
                except (TypeError, ValueError):
                    rec[key] = None
            else:
                rec[key] = None
        out.append(rec)
    # Sort ascending by fiscal_date; keep only last 5
    out.sort(key=lambda r: r.get("fiscal_date", ""))
    return out[-5:]


def _fetch_one(ticker: str, logger=None) -> Dict[str, Any]:
    """Fetch all six histories for one ticker. Returns {} on complete failure."""
    if yf is None:
        return {}
    result: Dict[str, Any] = {
        "quarterly": [],
        "annual": [],
        "balance_sheet_quarterly": [],
        "balance_sheet_annual": [],
        "cashflow_quarterly": [],
        "cashflow_annual": [],
    }
    try:
        stock = yf.Ticker(ticker)
    except Exception as e:
        if logger:
            logger.warning(f"  {ticker}: yf.Ticker failed: {e}")
        return result

    def _try(attr_name):
        try:
            return getattr(stock, attr_name)
        except Exception as e:
            if logger:
                logger.debug(f"  {ticker}: {attr_name} failed: {e}")
            return None

    result["annual"] = _records_from_df(_try("financials"), INCOME_FIELDS, "year")
    result["quarterly"] = _records_from_df(_try("quarterly_financials"), INCOME_FIELDS, "quarter")
    result["balance_sheet_annual"] = _records_from_df(_try("balance_sheet"), BALANCE_SHEET_FIELDS, "year")
    result["balance_sheet_quarterly"] = _records_from_df(_try("quarterly_balance_sheet"), BALANCE_SHEET_FIELDS, "quarter")
    result["cashflow_annual"] = _records_from_df(_try("cashflow"), CASHFLOW_FIELDS, "year")
    result["cashflow_quarterly"] = _records_from_df(_try("quarterly_cashflow"), CASHFLOW_FIELDS, "quarter")
    return result


def fetch_historical_financials(tickers, logger=None, sleep_seconds: float = 0.3) -> Dict[str, Any]:
    """
    Fetch historical financials for a list or dict of tickers.

    Accepts either an iterable of ticker symbols OR a dict keyed by ticker
    (common `market_data` shape). Returns a dict keyed by ticker.

    Observes the DNS-safety rule: sequential calls with small sleep between
    tickers to avoid macOS getaddrinfo thread exhaustion.
    """
    if hasattr(tickers, "keys"):  # dict-like
        symbols = [t for t in tickers.keys() if isinstance(tickers.get(t), dict)]
    else:
        symbols = list(tickers)

    if logger:
        logger.info(f"Fetching historical financials for {len(symbols)} tickers...")

    out: Dict[str, Any] = {}
    for i, t in enumerate(symbols):
        try:
            data = _fetch_one(t, logger)
            out[t] = data
            if logger:
                n_a = len(data.get("annual") or [])
                n_q = len(data.get("quarterly") or [])
                logger.info(f"  {t}: {n_a} annual / {n_q} quarterly income periods")
        except Exception as e:
            if logger:
                logger.warning(f"  {t}: historical financials failed: {e}")
            out[t] = {
                "quarterly": [], "annual": [],
                "balance_sheet_quarterly": [], "balance_sheet_annual": [],
                "cashflow_quarterly": [], "cashflow_annual": [],
            }
        if sleep_seconds and i < len(symbols) - 1:
            time.sleep(sleep_seconds)

    if logger:
        filled = sum(1 for t in out if out[t].get("quarterly") or out[t].get("annual"))
        logger.info(f"Historical financials: {filled}/{len(symbols)} tickers populated")
    return out
