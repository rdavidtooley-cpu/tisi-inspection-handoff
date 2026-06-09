---
name: Financial Model Update Methodology
description: How to correctly update quarterly financial models from 10-K filings — Q4 is always derived, never directly reported
type: feedback
originSessionId: 2a44e17f-f86e-4a9d-a4bc-21b00a38f01f
---
Companies never report Q4 standalone financials. They report full-year (10-K) and the first three quarters (10-Qs). Q4 standalone must always be calculated.

**Rule:** When updating a financial model after a 10-K is filed:
1. Enter the full-year figures in the FY annual column as hardcoded inputs (source: 10-K)
2. Use a formula for Q4 = FY - Q1 - Q2 - Q3
3. Never leave Q4 blank waiting for a "Q4 report" — it doesn't exist

**Why:** Robert corrected this on 2026-04-01 when TISI model had Q1–Q3 2025 populated but Q4 was empty. The correct workflow is always: 10-K drops → enter FY column → formula derives Q4.

**How to apply:** Applies to all company models (TISI, MG, and any future models). Income statement, cash flow, and any period-end balance sheet items all follow this pattern. The FY column is the 10-K source. Q4 is always a formula.

---

## CF Check Row — Ending Cash Must Match BS Cash

The row immediately below "Ending Cash Balance" in the CF section is the reconciliation check (CF ending cash − BS cash). If non-zero, the chain is broken.

**Rule:** Two causes of a non-zero check:
1. **Missing seed** — the first populated year's beginning cash (row 151) must be hardcoded to the prior year's ending cash from the 10-K. All subsequent years reference prior year's Ending Cash row via formula.
2. **Wrong CF item** — total CF change must equal actual BS cash movement year-over-year. Find the line item that doesn't match the 10-K disclosure.

**Why:** Both TISI and MG models had this issue — row 151 for the first year referenced an empty template column, making the entire cash chain garbage. Discovered 2026-04-03.

**How to apply:** After building or updating any model, verify the check row for all annual periods. Seed fix first (hardcode row 151 for earliest FY), then trace any residual to the specific bad CF line item.

---

## Audit by Formula Pattern, Not Just Label or Value

Model audits must include a formula-text check. For any flow-statement row (IS, CF, working capital changes), the Q4 formula must reference *that same row* in FY, Q1, Q2, Q3 — never another row's columns.

**Why:** TISI model had a template-level bug on 2026-05-10 where row 103 (Non-cash Interest Expense) Q4 formula was `=IFERROR(FY103−Q3_105−Q2_103−Q1_105,"")` — references mixed row 103 and row 105 (Other Expenses). Propagated across 8 Q4 columns (K, P, U, Z, AE, AJ, AO, AT) from 2018 onward via copy-paste. Manifested as $9–10K cash recon breaks in 2024Q4 and 2025Q4. Label-walking audits missed it because the cells still had formulas — just wrong ones.

**Rule:** For every Q4 cell on an input-driver row, verify the formula matches `\bFY{r}\b.*\bQ1{r}\b.*\bQ2{r}\b.*\bQ3{r}\b`. Anything else is suspect.

**How to apply:** Use `financial-analysis:audit-xls` at scope=model as the first-pass formula-pattern check on every model edit — fastest way to catch this class of error.

---

## Forecast-Column Circular References Hide Under IFERROR

Self-referencing formulas in projection columns won't show as errors if wrapped in IFERROR — but the math is broken in forecast periods. Historical actuals are unaffected, so the bug stays invisible until DCF/LRP work runs.

**Why:** TISI model had 50 self-referencing cells in projection cols AV–CC on rows 107 ("Pretax Cash Flow") and 113 ("Net Cash Flow"). Formula `=IFERROR(AV98−AV104+AV103−AV107,"")` references AV107 inside AV107. IFERROR suppressed the circular error; the model looked fine until audit-xls flagged it 2026-05-10.

**Rule:** Every model audit must scan for `cell_coordinate` appearing inside its own formula text, across the entire workbook including projection columns. `re.search(rf"\b{cell.coordinate}\b", cell.value)` on every formula cell.

**How to apply:** Before any DCF or long-range plan work, run audit-xls to catch hidden circulars. Our home-grown audit scripts (validate_model.py etc.) only check historical actuals — they don't catch forecast-period circulars.

---

## New Anthropic `financial-analysis` Skills vs. Home-Grown Audit Scripts

Tested `financial-analysis:audit-xls` (scope=model) on TISI_Model.xlsx 2026-05-10 alongside our existing audit infrastructure.

**The new skill caught what our scripts missed:**
- Template-level formula bugs propagated by copy-paste (lesson above)
- Forecast-column circulars hidden under IFERROR (lesson above)
- Hardcodes in cells that should be formulas (when those cells aren't on labeled rows)

**Our scripts still own:**
- Validating model values against the source filing (XBRL ties, line-by-line 10-K/10-Q diff)
- `audit_is_vs_xbrl.py` and `final_10k_comparison.py` in each model's `Models/` folder

**Workflow:**
1. Edit the model
2. Run `financial-analysis:audit-xls` at scope=model → integrity check
3. Fix any integrity issues
4. Run `audit_is_vs_xbrl.py` + `final_10k_comparison.py` → filing-content validation
5. Save

The new skill replaces the "is the model internally consistent?" job. Our scripts still own the "does the model match the filing?" job.

**Side note on recalc:** openpyxl edits don't recalculate cached values. After editing formulas, force recalc with `/opt/homebrew/bin/soffice --headless --calc --convert-to xlsx --outdir /tmp/x file.xlsx` then copy back. Required before any post-edit validation reads.

---

## Cross-Company Data Contamination — Always Diff Models Against Sister Models

When a project has multiple company models built from the same template (e.g., TISI_Model.xlsx and MG_Model.xlsx in Inspection_Intel), a prior session's accidental copy-paste can leave one model holding another company's quarterly data. The contamination won't show on FY annual reconciliation (since FY is hardcoded from the 10-K) but will show on quarterly cash recons as systematic mismatches across multiple years.

**Why:** MG_Model.xlsx had **107 cells** in its 2023-2025 Q1-Q3 quarterly CF section containing TISI's exact numeric values — CapEx, working capital changes, D&A, debt issuance costs, FX effects, etc. Discovered 2026-05-10 when MG's quarterly cash recons broke across every Q1-Q3 from 2023 through 2025 while every FY annual reconciled cleanly. MG and TISI are different companies with different cash profiles, so 107 numeric matches are not coincidence — they confirm contamination.

**Rule:** Whenever a model is refreshed, run a cross-workbook diff against every sister model in the project. Cell-by-cell comparison for exact-value matches in quarterly columns. Significant matches (more than a handful) confirm contamination and demand re-extraction from the company's own filings.

**How to apply:**
1. Load contaminated model and each sister model with `data_only=True`
2. For each quarterly column (Q1, Q2, Q3 across all years), check `mg_value == tisi_value and tisi_value not in (None, 0, "")` per cell
3. Tally matches. If >5-10 in a row's quarterly section, that row is contaminated.
4. To fix: extract period-only values from the company's own 10-Qs:
   - Q1 column: use Q1 10-Q's 3-month CF figures as-is
   - Q2 column: subtract Q1 from Q2 10-Q's 6-month YTD CF
   - Q3 column: subtract Q1+Q2 cumulative from Q3 10-Q's 9-month YTD CF
   - Q4 column: derives automatically via the FY − Q1 − Q2 − Q3 rule

This is now a required check in any model refresh workflow.

---

## SEC 10-Q Cash Flow Parser — BeautifulSoup Text Walker

Reliable pattern for extracting structured CF data from any SEC 10-Q HTML filing. Worked across 9 MG 10-Qs spanning 2023-2025 with zero modification.

**Algorithm:**
1. `BeautifulSoup(html, "html.parser").get_text("\n", strip=True)` to flatten the HTML
2. Locate CF section between `"cash flows from operating activities"` (lowercased) and `"supplemental"` (lowercased) markers
3. Tokenize: combine `"("` + `"N"` + `")"` three-line triples into single `"(N)"` tokens (for parenthesized negatives); drop `"$"` tokens
4. Walk tokens: accumulate non-numeric tokens as label buffer; when hitting a numeric, flush the buffer as the line label and pair this number + the next number as `(current_period_YTD, prior_period_YTD)`
5. Store as `{label: current_YTD_value}` dict

**Period-only computation from YTD 10-Q values:**
- Q1 column = Q1 10-Q figures (already 3-month)
- Q2 column = Q2 10-Q YTD − Q1 10-Q YTD
- Q3 column = Q3 10-Q YTD − Q2 10-Q YTD
- Q4 column = derived via FY (from 10-K) − Q1 − Q2 − Q3

**Don't try to parse rendered HTML tables** — XBRL is overkill, table structures vary, the text walker is robust across filers and years. Reference implementation in `MistrasGroup_MG/` cleanup session 2026-05-10.

**Canonical-to-model-row mapping is company-specific:**
- Build a `CANON_MAP = {canon_key: regex_pattern}` for the company's CF labels
- Build a `ROW_MAP = {model_row: lambda period_dict: ...}` that combines canonical keys (e.g., row 120 "Accrued" = accrued_chg + tax_payable_chg; row 131 "CapEx" = ppe_purchase + intang_purchase)
- Live alongside the workbook for re-use on future quarterly refreshes

**Always force LibreOffice recalc after openpyxl writes** — cached values are stale until Excel/LibreOffice opens and re-evaluates: `/opt/homebrew/bin/soffice --headless --calc --convert-to xlsx --outdir /tmp/recalc file.xlsx && cp /tmp/recalc/file.xlsx file.xlsx`.

This pattern is reusable for any Intel project (Oil_Gas, Casino, Metal_Mining) that builds quarterly financial models from SEC filings.

---

## Beginning Cash row 151 — annual columns must chain from prior YEAR ending

For annual columns in a quarterly+annual model, Beginning Cash formula (row 151) must reference the PRIOR ANNUAL column's row 152 ending, not the column immediately to the left (which is typically a Q4 quarterly column).

**Why:** MG model had L151 = `=IFERROR(K151,"")` — pulling from K151 (2018Q4 beg cash) instead of G152 (FY2017 end). K151 chained back through quarterly columns with contaminated data, producing a $10,339 propagating cash-recon delta across FY2018, FY2019, FY2020.

**Rule:** For every annual column letter `X`, row 151 formula must be `=IFERROR({prior_annual_col}152,"")`. The prior annual col is the most-recent FYE column to the left — NOT the prior quarterly column. For TISI/MG template: G (FY2017) ← prior is C or seed; L (FY2018) ← G; Q (FY2019) ← L; V (FY2020) ← Q; AA (FY2021) ← V; AF (FY2022) ← AA; AK (FY2023) ← AF; AP (FY2024) ← AK; AU (FY2025) ← AP.

**How to apply:** When auditing any annual cash chain, explicitly check every annual column's row 151 formula. If it references a quarterly column letter, it's broken. This is structurally different from cell-by-cell formula bugs — it's a chain-integrity issue that propagates errors forward through every subsequent year.

---

## Cross-Company FULL Historical Contamination

Sibling-template models (built by copying another company's workbook as a starting point) can have ENTIRE multi-year columns of the source company's data, not just partial contamination.

**Why:** MG model was built by copying TISI's template. The original author populated FY2021+ with MG data but never replaced FY2015-FY2020 — those 6 years remained 100% TISI data. Discovered 2026-05-11 via cell-by-cell cross-model diff: 685 cells matched TISI exactly across 6 annual columns. Earlier session-1 fix had caught only the quarterly CF contamination (107 cells) and missed this much larger annual contamination.

**Rule:** When auditing any sibling-template model, the cross-model diff must cover ALL period columns (every populated annual + quarterly), not just the recent quarters where contamination was first noticed. Cross-template-copy + partial-population leaves "first N years untouched" as a common pattern.

**How to apply:** Run a full diff: for each populated column, count cells where `model_A[r, col] == model_B[r, col] AND model_B[r, col] not in (0, None, "")`. Any column with >80% match is systemically contaminated. Rebuild requires sourcing the company's actual SEC filings (10-Ks going back as far as the model's earliest year) and re-populating IS + BS + CF for each contaminated year. May need to handle fiscal-year changes (e.g., MG transitioned from May year-end to December year-end via a 2016 7-month transition period — no clean calendar 2015/2016 data exists, so those columns should be cleared rather than synthesized).

---

## Forecast-Column Formula Templates Are Systematically Broken — Fix As A Class

When the financial-model template has forecast columns (typically extending past the last historical annual), those columns' formulas are often broken throughout — section subtotals point at wrong rows, self-references create circulars, sum ranges include header/subtotal rows causing double-counting. The bugs don't surface during normal forecast use because forecast inputs are zero/empty (formulas resolve to 0 via IFERROR). They only surface when actual values are loaded into the column.

**Why:** TISI and MG forecast columns (AV–BT, 28 cols) had broken formulas at: row 107 (Pretax CF), 113 (Net CF), 116 (WC chg), 122 (Other non-cash), 126 (Total non-cash), 128 (CFO), 135 (Investing total), 146 (Financing total), 150 (Change in Cash), 152 (Ending Cash), 164 (Total Curr Assets), 170 (Total Assets — double-counted subtotal row 164), 177 (Total Curr Liab), 182 (Total Liab), 190 (Total Equity), 192 (TL+E — referenced row 204 which doesn't exist), 193 (BS check). Every row had wrong cell references in the forecast pattern that worked correctly in the historical pattern.

**Rule:** When converting a forecast column to an actuals column (e.g., loading Q1 2026 into AV), do NOT just write data into the cells. Replace every structural-row formula in the target column with the historical-column equivalent (column-letter substitution). Copy from the most recent historical annual (AU for FY2025) and substitute the target column letter.

**How to apply:** Before loading actuals into any forecast column, diff every formula in the target column against the most recent historical annual column. Any formula where the row references differ (independent of the column letter substitution) needs replacement with the historical pattern. Build a one-time helper `copy_historical_pattern_to(target_col)` that does the AU→target substitution for all critical structural rows. Run it every time a forecast column is being converted to actuals — saves manual debugging each quarterly refresh.

**Robert's "5 cols away" archive workflow:** when converting a forecast column to actuals, his standard process is to copy the current forecast values+formats about 5 columns to the right of the current structure (one fiscal-year worth of cols), preserving the original estimate as a frozen record before overwriting the original column with actuals. Apply this when forecast values exist; skip when forecast is effectively empty (as was the case for MG's AV in May 2026).

---

## SEC HTML Parens-as-Negatives — Three Formats, Tokenizer Must Handle All

SEC 10-K/10-Q HTML financial-statement tables represent negative numbers via parentheses, but the HTML rendering produces THREE different format patterns depending on filing vintage. A tokenizer that only handles one (or two) silently drops values, manifesting as "missing CF line items" downstream.

**The three formats:**

- **Format A (2023+ modern filings):** `(N)` as a single line/token. Direct parse: `parse_amt("(1,234)")` → -1234.
- **Format B (some 2018-2022 filings):** Three separate lines/tokens — `(`, `N`, `)`. Tokenizer must combine into `(N)`.
- **Format C (common 2018-2022 filings):** Two lines/tokens — `(N` (open-paren attached to the number), then `)` alone on the next line. **THIS IS THE COMMONLY-MISSED ONE.**

**Why this matters:** Working-capital changes in any quarter (AR change, Inventory change, AP change, Accrued change, prepaid expenses) are mostly negative. If the tokenizer misses format C, EVERY negative WC line returns None, and the model's WC bridge becomes 0 in those quarters. The cash recon breaks by exactly the sum of missing negatives — but the bug is subtle because positives and "—" still parse correctly.

**Tokenizer reference implementation:**

```python
def tokenize(lines):
    out = []
    i = 0
    while i < len(lines):
        l = lines[i]
        # Format B: "(" + "N" + ")" three-token pattern
        if l == "(" and i+2 < len(lines) and lines[i+2] == ")":
            out.append("(" + lines[i+1] + ")")
            i += 3
        # Format C: "(N" + ")" two-token pattern  ← critical for older filings
        elif l.startswith("(") and len(l) > 1 and i+1 < len(lines) and lines[i+1] == ")":
            out.append(l + ")")
            i += 2
        # Format A: "(N)" already combined — passes through
        elif l == "$":
            i += 1
        else:
            out.append(l)
            i += 1
    return out
```

**How to apply:** Any SEC parser must validate against filings from multiple vintages. Quick smoke test: parse a Q1 10-Q's working-capital section (AR, Inv, AP, Accrued changes — always a mix of negatives). If any returns None when the 10-Q clearly shows `(1,234)`, the tokenizer is missing format C. Especially relevant for any rebuild of pre-2023 financial history — the parser pattern in [SEC 10-Q CF Parser](#sec-10-q-cash-flow-parser--beautifulsoup-text-walker) above needs the format-C handler appended before use on older filings.

---

## SEC Income Statement Parser — Two Critical Regex Traps

When parsing SEC income statements across multiple filing vintages, two regex traps cause silent failures that break downstream cash recon. Both surfaced during MG quarterly historic rebuild (2018-2022).

### Trap 1: Tax regex matching the pretax-label substring

The PRETAX label is typically "Loss before benefit for income taxes" or "Income before provision for income taxes". The TAX label is "Benefit for income taxes" or "Provision for income taxes" alone.

A naive tax regex like `(provision|benefit).{0,30}for income tax` with `re.search()` matches BOTH labels — because the pretax label contains the substring "benefit for income tax" or "provision for income tax". When CANON_IS is walked per-label with first-match-wins, the pretax label may be processed first (depending on order), assigning its value to the tax row. Result: tax = pretax value (e.g., -$114,017 instead of -$15,495), and the cash recon breaks by the missing tax effect.

**Rule:** Tax regex must anchor at start with `^`: `^(provision|benefit).{0,15}for income tax`. The anchor prevents matching pretax labels that happen to contain "benefit for income tax" as a substring.

**Edge case:** Some filings format the tax line as `"(Benefit) provision for income taxes"` (parenthetical leading the words). Handle with: `^\(?(benefit|provision)\)?\s+(provision|benefit)?.{0,15}for income tax`.

### Trap 2: IS section title varies — "Statements of Loss" exists

Modern filings title the IS table "Consolidated Statements of Income" or "Statements of Operations". But when a company posts losses, some filings use "Statements of Loss" or "Statements of (Loss) Income" (MG's 2021Q1 and 2022Q1 10-Qs do this). A parser anchored only on "income" or "operations" silently MISSES the entire IS for those filings — returns empty dict.

**Rule:** Don't anchor IS extraction on the section title. Anchor on a phrase reliably present in the IS table body itself — `"Cost of revenue"` works for any company that reports cost-of-revenue accounting. Find the FIRST occurrence of `"Cost of revenue"` in the document, back up ~300 chars to locate the `"Revenue"` label that starts the table, parse from there.

**How to apply:**
- Validate any SEC IS parser against at least one money-losing-year filing (where "Statements of Loss" titles appear)
- Validate against at least one filing where the company has a tax BENEFIT (negative tax expense)
- MG 2020Q1 and 2021Q1 are good test fixtures: 2020Q1 has the "Benefit for income taxes (15,495)" line, 2021Q1 has the "Statements of Loss" title.

These two traps surface together in money-losing periods, which is precisely when accurate IS parsing matters most (impairment quarters, recession quarters, restructuring quarters).
