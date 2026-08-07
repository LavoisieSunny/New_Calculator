"""
backend/justification_engine.py

Deterministic, Python-first "Justify Compensation" engine.

This module implements the plan agreed for hardening the existing
is_justify feature in backend/main.py:

  STEP 0 - resolve_case_data()         : 3-tier field resolution
            (user-edited form value -> on-demand OCR re-parse -> blank)
  STEP 1 - resolve_tribunal_total()    : regex -> targeted LLM -> insufficient
  STEP 2 - resolve_calculator_total()  : always recomputed server-side,
            never trusts the frontend's cached calculator_result
  STEP 3 - run_death_hypothesis_grid() / solve_injury_formula()
  STEP 4 - build_headwise_comparison() : per-head Low/Adequate/High table,
            sourced from the deterministic parser, not an LLM re-reading OCR

Public entrypoint: build_justification(parsed_fields, calculator_result, ocr_text)

The return value is STRUCTURED DATA (a plain dict of numbers/strings), not
prose. backend/main.py is responsible for (a) optionally handing this dict
to the LLM as pre-verified facts to narrate, and (b) returning it directly
in the API response so the frontend can render it as a table instead of
only as chat-bubble text.

No network/LLM call in this module is required for the happy path -- the
only LLM dependency is the small, targeted fallback in
resolve_tribunal_total() (Step 1b/1c), and even that fails soft (returns
None) if Ollama is unreachable, so callers can degrade to
"insufficient data" instead of raising.
"""

import re
import logging
from typing import Optional

from backend.calculator import (
    calculate_death_compensation,
    calculate_injury_compensation,
    get_multiplier,
    safe_float,
    safe_int,
)
from backend.parser_heuristics import (
    parse_extracted_text,
    format_suggestions_for_calculator,
    extract_compensation_table_fields,
    parse_compensation_table,
)

logger = logging.getLogger("backend.justification_engine")


# ──────────────────────────────────────────────────────────────────────────
# Small adapter so we can call calculate_death_compensation /
# calculate_injury_compensation (which expect a CompensationRequest-shaped
# object with attribute access) using a plain dict of resolved fields.
# Any attribute not present on the dict resolves to None, matching how the
# real pydantic model treats unset optional fields.
# ──────────────────────────────────────────────────────────────────────────
class _CalcInput:
    def __init__(self, d: dict):
        self.__dict__.update(d or {})

    def __getattr__(self, item):
        return None


def _is_blank(v) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == "")


# ──────────────────────────────────────────────────────────────────────────
# STEP 0 — Resolve case data (age, income, marital_status, dependents,
# disability, future_type, ...) using the 3-tier priority:
#   1. user-edited form value (non-blank)          -> trust it
#   2. else, on-demand OCR re-parse (same parser as autofill, just invoked
#      here instead of requiring the button)         -> use it
#   3. else                                           -> stays blank
# ──────────────────────────────────────────────────────────────────────────
_DEATH_FIELDS = [
    "age", "monthly_income", "marital_status", "dependents", "future_type",
    "future_prospect", "consortium", "consortium_claimants", "funeral_expenses",
    "loss_estate", "medical_expenses", "award_date", "date_of_accident",
    "conlum", "conspo", "conpar", "conchil", "conwif", "conmo", "confath",
    "conhus", "conbro", "consis",
]
_INJURY_FIELDS = [
    "age", "monthly_income", "disability", "dependents", "medical_expenses",
    "future_medical_expenses", "pain_and_suffering", "transportation",
    "special_diet", "attender_charges", "loss_of_income",
    "coliti", "misex", "loamiti", "lopmarri", "loexlife", "loveaff", "lossofenjoy",
]


def resolve_case_data(parsed_fields: dict | None, ocr_text: str | None, case_type_hint: str | None = None):
    """
    Returns (resolved_fields: dict, field_sources: dict[str, "form"|"ocr_reparse"|"unresolved"], reparsed_case_type: str|None)
    """
    parsed_fields = dict(parsed_fields or {})
    resolved: dict = {}
    sources: dict = {}

    reparsed_fields: dict = {}
    reparsed_case_type = None
    reparsed_award = None

    if ocr_text and ocr_text.strip():
        try:
            suggestions = parse_extracted_text(ocr_text.split("\n"), case_type=case_type_hint)
            formatted = format_suggestions_for_calculator(suggestions)
            reparsed_case_type = formatted.get("case_type")
            reparsed_fields = formatted.get("fields", {}) or {}
            reparsed_award = formatted.get("total_compensation")
        except Exception:
            # This covers "Ollama down" and any parser edge case -- Step 0
            # must never raise; it just falls through to fewer resolved
            # fields, same as if no PDF had been uploaded.
            logger.exception("justification_engine: on-demand OCR re-parse failed")

    all_keys = set(list(parsed_fields.keys()) + list(reparsed_fields.keys()) + _DEATH_FIELDS + _INJURY_FIELDS)
    for key in all_keys:
        if key == "award_amount":
            continue  # handled separately below, together with total_compensation
        form_val = parsed_fields.get(key)
        if not _is_blank(form_val):
            resolved[key] = form_val
            sources[key] = "form"
        elif not _is_blank(reparsed_fields.get(key)):
            resolved[key] = reparsed_fields.get(key)
            sources[key] = "ocr_reparse"
        else:
            resolved[key] = None
            sources[key] = "unresolved"

    # award_amount / total_compensation: same 3-tier priority, kept separate
    # because the parser's output key is "total_compensation" while the
    # frontend's cached field is historically called "award_amount".
    form_award = parsed_fields.get("award_amount") or parsed_fields.get("total_compensation")
    if not _is_blank(form_award):
        resolved["award_amount"] = form_award
        sources["award_amount"] = "form"
    elif not _is_blank(reparsed_award):
        resolved["award_amount"] = reparsed_award
        sources["award_amount"] = "ocr_reparse"
    else:
        resolved["award_amount"] = None
        sources["award_amount"] = "unresolved"

    return resolved, sources, reparsed_case_type


# ──────────────────────────────────────────────────────────────────────────
# STEP 1 — Resolve the tribunal's awarded total.
#   1a. regex extraction straight from ocr_text (fast, zero LLM dependency)
#   1b. targeted, single-purpose LLM call -- ONLY if regex found nothing
#   1c. "insufficient data" -- never guessed
# (Step 0's resolved award_amount is checked first since it's effectively
# "free" -- either the user's own edited value or an already-successful
# on-demand re-parse.)
# ──────────────────────────────────────────────────────────────────────────
_AWARD_PATTERNS = [
    r'total\s+compensation\s*(?:of\s*)?(?:rs\.?|inr|rupees)\s*([\d,]{4,10})',
    r'award\s+amount\s*(?:of\s*)?(?:rs\.?|inr|rupees)\s*([\d,]{4,10})',
    r'compensation\s+amount\s*(?:of\s*)?(?:rs\.?|inr|rupees)\s*([\d,]{4,10})',
    r'tribunal\s+(?:has\s+)?awarded\s*(?:rs\.?|inr|rupees)\s*([\d,]{4,10})',
    r'(?:^|\n)\s*total\s*[:\-]?\s*(?:rs\.?|inr|rupees)\s*([\d,]{4,10})\s*/?-?\s*(?:\n|$)',
]


def extract_award_total_regex(ocr_text: str) -> Optional[float]:
    """
    Same pattern set as main._fallback_extract_award_total(), kept here so
    the justification engine is self-contained. Prefers the LAST anchored
    match in reading order, since the final award figure is almost always
    stated near the end of a judgment, after the reasoning.
    """
    if not ocr_text:
        return None
    candidates = []
    for pat in _AWARD_PATTERNS:
        for m in re.finditer(pat, ocr_text, re.IGNORECASE | re.MULTILINE):
            raw = m.group(1).replace(",", "").strip()
            try:
                val = float(raw)
            except ValueError:
                continue
            if val >= 1000:  # compensation figures are never sub-Rs.1000
                candidates.append((m.start(), val))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0])
    return candidates[-1][1]


def _llm_extract_award_total(ocr_text: str) -> Optional[float]:
    """
    Small, targeted LLM call -- asks for exactly one number, not a full
    re-extraction. Fails soft (returns None) if Ollama is unreachable so
    the caller can fall back to "insufficient data" instead of degrading
    silently or raising.
    """
    try:
        from backend.llm_client import generate_response
        snippet = ocr_text[-6000:] if len(ocr_text) > 6000 else ocr_text
        prompt = (
            "Find ONLY the final total compensation amount awarded by the "
            "tribunal in the judgment text below. Reply with the number only "
            "(digits, no commas, no currency symbol, no words). If no such "
            "figure is stated, reply with exactly: NONE.\n\n"
            f"JUDGMENT TEXT:\n{snippet}"
        )
        raw = generate_response(
            prompt,
            system_instruction=(
                "You extract a single number. Never invent a figure that is "
                "not literally present in the text."
            ),
        )
        raw = (raw or "").strip()
        if not raw or raw.upper().startswith("NONE") or "Error communicating with LLM client" in raw:
            return None
        m = re.search(r'[\d,]{4,10}', raw)
        if not m:
            return None
        val = float(m.group(0).replace(",", ""))
        return val if val >= 1000 else None
    except Exception:
        logger.warning(
            "justification_engine: targeted LLM award extraction unavailable "
            "(Ollama unreachable?) -- degrading to insufficient data",
            exc_info=True,
        )
        return None


def resolve_tribunal_total(resolved_fields: dict, ocr_text: str | None) -> dict:
    """Returns {"value": float|None, "source": str|None, "confidence": "high"|"medium"|"low"}"""
    form_val = resolved_fields.get("award_amount")
    try:
        form_total = float(form_val) if not _is_blank(form_val) else 0.0
    except (TypeError, ValueError):
        form_total = 0.0

    if form_total > 0:
        return {"value": form_total, "source": "workstation field / on-demand OCR re-parse", "confidence": "high"}

    regex_total = extract_award_total_regex(ocr_text or "")
    if regex_total:
        return {"value": regex_total, "source": "regex extraction from OCR text", "confidence": "high"}

    if ocr_text and ocr_text.strip():
        llm_total = _llm_extract_award_total(ocr_text)
        if llm_total:
            return {"value": llm_total, "source": "targeted LLM extraction (fallback)", "confidence": "medium"}

    return {"value": None, "source": None, "confidence": "low"}


# ──────────────────────────────────────────────────────────────────────────
# STEP 2 — Recompute the calculator total server-side, ALWAYS, from the
# Step 0 resolved inputs. Never trusts calculator_result.final_amount as
# sent by the frontend (it can be stale if the user edited a field without
# re-clicking "Calculate").
# ──────────────────────────────────────────────────────────────────────────
def resolve_calculator_total(resolved_fields: dict, case_type: str) -> dict:
    calc_input = _CalcInput(resolved_fields)
    if case_type == "death":
        return calculate_death_compensation(calc_input)
    return calculate_injury_compensation(calc_input)


# ──────────────────────────────────────────────────────────────────────────
# STEP 3 (death) — Hypothesis grid.
# Death compensation mixes four interacting levers into one lump
# loss_of_dependency figure, so we grid-search marital_status / dependents /
# future_type (age & income held fixed as the least-disputed facts) for the
# combination whose output lands closest to the tribunal's actual total.
# ──────────────────────────────────────────────────────────────────────────
_MARITAL_OPTIONS = ["married", "bachelor"]
_FUTURE_TYPE_OPTIONS = [1, 2]  # 1 = permanent job, 2 = self-employed/daily wage


def run_death_hypothesis_grid(resolved_fields: dict, tribunal_total: float, dependents_range=range(0, 8)) -> dict:
    base = dict(resolved_fields)
    results = []
    for marital in _MARITAL_OPTIONS:
        for dependents in dependents_range:
            for future_type in _FUTURE_TYPE_OPTIONS:
                trial = dict(base)
                trial["marital_status"] = marital
                trial["dependents"] = dependents
                trial["future_type"] = future_type
                breakdown = calculate_death_compensation(_CalcInput(trial))
                diff = breakdown["final_amount"] - tribunal_total
                results.append({
                    "marital_status": marital,
                    "dependents": dependents,
                    "future_type": future_type,
                    "calculated_total": breakdown["final_amount"],
                    "diff_from_tribunal": round(diff, 2),
                    "abs_diff": abs(diff),
                })
    results.sort(key=lambda r: r["abs_diff"])
    best = results[0] if results else None
    near_ties = []
    if best:
        near_ties = [r for r in results[1:6] if r["abs_diff"] <= best["abs_diff"] * 1.05 + 1]
    return {"best_match": best, "near_ties": near_ties, "grid_size": len(results)}


# ──────────────────────────────────────────────────────────────────────────
# STEP 3 (injury) — Track 1: the one formula-driven head
#   future_income_loss = monthly_income * 12 * (disability% / 100) * multiplier(age)
# Priority: direct text statement -> algebraic back-solve -> small grid
# (last resort, labeled "estimated, not derived") -> not derivable.
# ──────────────────────────────────────────────────────────────────────────
_DISABILITY_STATEMENT_PATTERNS = [
    r'functional\s+disability\s+(?:was\s+)?assessed\s+at\s+(\d{1,3}(?:\.\d+)?)\s*%',
    r'loss\s+of\s+earning\s+capacity\s+(?:was\s+)?held\s+at\s+(\d{1,3}(?:\.\d+)?)\s*%',
    r'vocational\s+disability\s+(?:of|at)\s+(\d{1,3}(?:\.\d+)?)\s*%',
    r'functional\s+disability\s+of\s+(\d{1,3}(?:\.\d+)?)\s*%',
]


def _extract_stated_disability_pct(ocr_text: str) -> Optional[float]:
    for pat in _DISABILITY_STATEMENT_PATTERNS:
        m = re.search(pat, ocr_text, re.IGNORECASE)
        if m:
            try:
                val = float(m.group(1))
                if 0 < val <= 100:
                    return val
            except ValueError:
                continue
    return None


def solve_injury_formula(resolved_fields: dict, ocr_text: str, tribunal_future_loss_head: Optional[float]) -> dict:
    age = safe_int(resolved_fields.get("age"), 30)
    monthly_income = safe_float(resolved_fields.get("monthly_income"), 0.0)
    claimed_disability = safe_float(resolved_fields.get("disability"), 0.0)
    multiplier = get_multiplier(age)

    # 1. Direct text extraction of the tribunal's own stated finding.
    stated_pct = _extract_stated_disability_pct(ocr_text or "")
    if stated_pct is not None:
        return {
            "method": "direct_text_extraction",
            "tribunal_disability_percent": stated_pct,
            "claimed_disability_percent": claimed_disability,
            "note": "Tribunal's stated functional/vocational disability found directly in the judgment text -- a hard fact, not an inference.",
        }

    # 2. Algebraic back-solve -- only one unknown left once the award table
    # isolates this head and income/multiplier are treated as undisputed.
    if tribunal_future_loss_head and tribunal_future_loss_head > 0 and monthly_income > 0 and multiplier > 0:
        implied_pct = (tribunal_future_loss_head / (monthly_income * 12 * multiplier)) * 100
        return {
            "method": "algebraic_back_solve",
            "tribunal_disability_percent": round(implied_pct, 2),
            "claimed_disability_percent": claimed_disability,
            "note": "Derived exactly from the isolated award-table figure for this head; monthly income and multiplier(age) treated as undisputed.",
        }

    # 3. Small grid -- last resort, both unknowns genuinely uncertain.
    if tribunal_future_loss_head and tribunal_future_loss_head > 0 and multiplier > 0:
        grid = []
        for pct_guess in range(5, 101, 5):
            implied_income = tribunal_future_loss_head / ((pct_guess / 100.0) * 12 * multiplier)
            grid.append({"disability_percent_guess": pct_guess, "implied_monthly_income": round(implied_income, 2)})
        return {
            "method": "grid_estimate",
            "grid": grid,
            "note": "ESTIMATED, NOT DERIVED -- both income and disability are uncertain, so this is a last-resort search, not an exact answer.",
        }

    # 4. Award table never isolates this head at all.
    return {
        "method": "not_derivable",
        "note": "Per-head breakdown for future loss of earning capacity is not available in this judgment; only total-level comparison is possible.",
    }


# ──────────────────────────────────────────────────────────────────────────
# STEP 4 — Head-wise comparison table (both case types), sourced from the
# deterministic parser's award-table extraction (extract_compensation_table_fields),
# NOT from an LLM re-reading the OCR text.
# ──────────────────────────────────────────────────────────────────────────
_HEAD_LABELS = {
    "medical_expenses": "Medical Expenses",
    "future_medical_expenses": "Future Medical Expenses",
    "pain_and_suffering": "Pain & Suffering",
    "transportation": "Transportation",
    "special_diet": "Special Diet",
    "attender_charges": "Attender Charges",
    "loss_of_income": "Loss of Income (special)",
    "consortium": "Loss of Consortium",
    "funeral_expenses": "Funeral Expenses",
    "loss_estate": "Loss to Estate",
}

_INJURY_DISCRETIONARY_HEADS = [
    "medical_expenses", "future_medical_expenses", "pain_and_suffering",
    "transportation", "special_diet", "attender_charges", "loss_of_income",
]
_DEATH_DISCRETIONARY_HEADS = ["consortium", "funeral_expenses", "loss_estate", "medical_expenses"]


_INJURY_HEAD_KEYWORDS = {
    "medical_expenses": ["medical expense", "medical treatment", "treatment expense", "इलाज व्यय", "चिकित्सा व्यय", "चिकित्सा"],
    "future_medical_expenses": ["future medical", "future treatment", "भविष्य में चिकित्सा", "भविष्य के इलाज"],
    "pain_and_suffering": ["pain and suffering", "pain & suffering", "पीड़ा", "शारीरिक एवं मानसिक"],
    "transportation": ["transportation", "conveyance", "travel expense", "आवागमन", "यात्रा व्यय"],
    "special_diet": ["special diet", "nutritious diet", "पोषक आहार", "पोष्टिक आहार"],
    "attender_charges": ["attender", "attendant", "nursing charge", "सहायक"],
    "loss_of_income": ["loss of income", "loss of earning", "आय की हानि"],
}


def _fuzzy_map_injury_head(label: str) -> Optional[str]:
    label_lower = label.lower()
    for canonical, keywords in _INJURY_HEAD_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in label_lower:
                return canonical
    return None


def extract_injury_headwise_table(ocr_text: str) -> dict:
    """
    extract_compensation_table_fields() only extracts DEATH-case heads
    (consortium/funeral/estate/multiplier) -- for injury cases it never
    populates medical/transport/attender/etc. So for injury we instead run
    the generic parse_compensation_table() over the OCR text and fuzzy-map
    its free-form head labels onto the canonical injury head keys the
    calculator uses. This is what gives build_headwise_comparison() real
    tribunal figures to compare against for injury cases, instead of
    everything showing up as "not separately itemized".
    """
    raw_table = parse_compensation_table(ocr_text or "")
    mapped = {}
    for label, val in raw_table.items():
        canonical = _fuzzy_map_injury_head(label)
        if canonical and canonical not in mapped:
            mapped[canonical] = val
    return mapped


def build_headwise_comparison(case_type: str, calc_breakdown: dict, tribunal_table_fields: dict) -> list:
    heads = _INJURY_DISCRETIONARY_HEADS if case_type == "injury" else _DEATH_DISCRETIONARY_HEADS
    rows = []
    for head in heads:
        calc_val = calc_breakdown.get(head)
        tribunal_val = tribunal_table_fields.get(head)
        label = _HEAD_LABELS.get(head, head.replace("_", " ").title())

        if tribunal_val is None:
            rows.append({
                "head": label, "calculator_amount": calc_val,
                "tribunal_amount": None, "verdict": "Not separately itemized",
            })
            continue

        try:
            tribunal_val_f = float(tribunal_val)
            calc_val_f = float(calc_val or 0)
        except (TypeError, ValueError):
            rows.append({"head": label, "calculator_amount": calc_val, "tribunal_amount": tribunal_val, "verdict": "N/A"})
            continue

        if abs(tribunal_val_f - calc_val_f) < 1:
            verdict = "Adequate"
        elif tribunal_val_f < calc_val_f:
            verdict = "Low"
        else:
            verdict = "High"

        rows.append({
            "head": label, "calculator_amount": calc_val_f,
            "tribunal_amount": tribunal_val_f, "verdict": verdict,
        })
    return rows


# ──────────────────────────────────────────────────────────────────────────
# STEP 5 (injury only) — Treatment-location vs. residence mismatch.
# If the injured person was treated in a different district/state than
# their home district/state, that's independent evidence supporting
# Transportation and Attender Charges -- regardless of what the disability
# formula analysis (Track 1) says. Matching is done at district/state
# level only (never full address), since OCR'd street-level addresses will
# always differ even for someone treated locally, and Hindi/English
# spelling variants make full-string matching unreliable.
#
# NOTE: _DISTRICT_STATE_GAZETTEER below is a practical, NOT exhaustive,
# starter list (all MP districts + major out-of-state cities that commonly
# show up in MP tribunal judgments). Extend it with more districts/states
# as your document set requires.
# ──────────────────────────────────────────────────────────────────────────
_DISTRICT_STATE_GAZETTEER = {
    # MP districts (english + hindi alias -> (canonical district, state))
    "mandla": ("Mandla", "Madhya Pradesh"), "मंडला": ("Mandla", "Madhya Pradesh"),
    "jabalpur": ("Jabalpur", "Madhya Pradesh"), "जबलपुर": ("Jabalpur", "Madhya Pradesh"),
    "indore": ("Indore", "Madhya Pradesh"), "इंदौर": ("Indore", "Madhya Pradesh"),
    "bhopal": ("Bhopal", "Madhya Pradesh"), "भोपाल": ("Bhopal", "Madhya Pradesh"),
    "gwalior": ("Gwalior", "Madhya Pradesh"), "ग्वालियर": ("Gwalior", "Madhya Pradesh"),
    "ujjain": ("Ujjain", "Madhya Pradesh"), "उज्जैन": ("Ujjain", "Madhya Pradesh"),
    "sagar": ("Sagar", "Madhya Pradesh"), "सागर": ("Sagar", "Madhya Pradesh"),
    "rewa": ("Rewa", "Madhya Pradesh"), "रीवा": ("Rewa", "Madhya Pradesh"),
    "satna": ("Satna", "Madhya Pradesh"), "सतना": ("Satna", "Madhya Pradesh"),
    "katni": ("Katni", "Madhya Pradesh"), "कटनी": ("Katni", "Madhya Pradesh"),
    "chhindwara": ("Chhindwara", "Madhya Pradesh"), "छिंदवाड़ा": ("Chhindwara", "Madhya Pradesh"),
    "balaghat": ("Balaghat", "Madhya Pradesh"), "बालाघाट": ("Balaghat", "Madhya Pradesh"),
    "seoni": ("Seoni", "Madhya Pradesh"), "सिवनी": ("Seoni", "Madhya Pradesh"),
    "narsinghpur": ("Narsinghpur", "Madhya Pradesh"), "नरसिंहपुर": ("Narsinghpur", "Madhya Pradesh"),
    "damoh": ("Damoh", "Madhya Pradesh"), "दमोह": ("Damoh", "Madhya Pradesh"),
    "panna": ("Panna", "Madhya Pradesh"), "पन्ना": ("Panna", "Madhya Pradesh"),
    "chhatarpur": ("Chhatarpur", "Madhya Pradesh"), "छतरपुर": ("Chhatarpur", "Madhya Pradesh"),
    "tikamgarh": ("Tikamgarh", "Madhya Pradesh"), "टीकमगढ़": ("Tikamgarh", "Madhya Pradesh"),
    "shahdol": ("Shahdol", "Madhya Pradesh"), "शहडोल": ("Shahdol", "Madhya Pradesh"),
    "sidhi": ("Sidhi", "Madhya Pradesh"), "सीधी": ("Sidhi", "Madhya Pradesh"),
    "singrauli": ("Singrauli", "Madhya Pradesh"), "सिंगरौली": ("Singrauli", "Madhya Pradesh"),
    "dindori": ("Dindori", "Madhya Pradesh"), "डिंडोरी": ("Dindori", "Madhya Pradesh"),
    "mandsaur": ("Mandsaur", "Madhya Pradesh"), "मंदसौर": ("Mandsaur", "Madhya Pradesh"),
    "ratlam": ("Ratlam", "Madhya Pradesh"), "रतलाम": ("Ratlam", "Madhya Pradesh"),
    "dewas": ("Dewas", "Madhya Pradesh"), "देवास": ("Dewas", "Madhya Pradesh"),
    "shajapur": ("Shajapur", "Madhya Pradesh"), "शाजापुर": ("Shajapur", "Madhya Pradesh"),
    "vidisha": ("Vidisha", "Madhya Pradesh"), "विदिशा": ("Vidisha", "Madhya Pradesh"),
    "raisen": ("Raisen", "Madhya Pradesh"), "रायसेन": ("Raisen", "Madhya Pradesh"),
    "sehore": ("Sehore", "Madhya Pradesh"), "सीहोर": ("Sehore", "Madhya Pradesh"),
    "hoshangabad": ("Hoshangabad", "Madhya Pradesh"), "narmadapuram": ("Hoshangabad", "Madhya Pradesh"),
    "betul": ("Betul", "Madhya Pradesh"), "बैतूल": ("Betul", "Madhya Pradesh"),
    "harda": ("Harda", "Madhya Pradesh"), "हरदा": ("Harda", "Madhya Pradesh"),
    "khandwa": ("Khandwa", "Madhya Pradesh"), "खंडवा": ("Khandwa", "Madhya Pradesh"),
    "khargone": ("Khargone", "Madhya Pradesh"), "खरगोन": ("Khargone", "Madhya Pradesh"),
    "barwani": ("Barwani", "Madhya Pradesh"), "बड़वानी": ("Barwani", "Madhya Pradesh"),
    "dhar": ("Dhar", "Madhya Pradesh"), "धार": ("Dhar", "Madhya Pradesh"),
    "jhabua": ("Jhabua", "Madhya Pradesh"), "झाबुआ": ("Jhabua", "Madhya Pradesh"),
    "alirajpur": ("Alirajpur", "Madhya Pradesh"), "अलीराजपुर": ("Alirajpur", "Madhya Pradesh"),
    "guna": ("Guna", "Madhya Pradesh"), "गुना": ("Guna", "Madhya Pradesh"),
    "ashoknagar": ("Ashoknagar", "Madhya Pradesh"), "अशोकनगर": ("Ashoknagar", "Madhya Pradesh"),
    "shivpuri": ("Shivpuri", "Madhya Pradesh"), "शिवपुरी": ("Shivpuri", "Madhya Pradesh"),
    "datia": ("Datia", "Madhya Pradesh"), "दतिया": ("Datia", "Madhya Pradesh"),
    "bhind": ("Bhind", "Madhya Pradesh"), "भिंड": ("Bhind", "Madhya Pradesh"),
    "morena": ("Morena", "Madhya Pradesh"), "मुरैना": ("Morena", "Madhya Pradesh"),
    "sheopur": ("Sheopur", "Madhya Pradesh"), "श्योपुर": ("Sheopur", "Madhya Pradesh"),
    "anuppur": ("Anuppur", "Madhya Pradesh"), "अनूपपुर": ("Anuppur", "Madhya Pradesh"),
    "umaria": ("Umaria", "Madhya Pradesh"), "उमरिया": ("Umaria", "Madhya Pradesh"),
    "burhanpur": ("Burhanpur", "Madhya Pradesh"), "बुरहानपुर": ("Burhanpur", "Madhya Pradesh"),
    "agar malwa": ("Agar Malwa", "Madhya Pradesh"), "niwari": ("Niwari", "Madhya Pradesh"),
    # major out-of-state cities/districts commonly seen in MP judgments
    "nagpur": ("Nagpur", "Maharashtra"), "नागपुर": ("Nagpur", "Maharashtra"),
    "mumbai": ("Mumbai", "Maharashtra"), "मुंबई": ("Mumbai", "Maharashtra"),
    "pune": ("Pune", "Maharashtra"), "पुणे": ("Pune", "Maharashtra"),
    "raipur": ("Raipur", "Chhattisgarh"), "रायपुर": ("Raipur", "Chhattisgarh"),
    "delhi": ("Delhi", "Delhi"), "दिल्ली": ("Delhi", "Delhi"), "new delhi": ("Delhi", "Delhi"),
    "ahmedabad": ("Ahmedabad", "Gujarat"), "अहमदाबाद": ("Ahmedabad", "Gujarat"),
    "hyderabad": ("Hyderabad", "Telangana"), "हैदराबाद": ("Hyderabad", "Telangana"),
    "lucknow": ("Lucknow", "Uttar Pradesh"), "लखनऊ": ("Lucknow", "Uttar Pradesh"),
    "kanpur": ("Kanpur", "Uttar Pradesh"), "कानपुर": ("Kanpur", "Uttar Pradesh"),
    "varanasi": ("Varanasi", "Uttar Pradesh"),
    "jaipur": ("Jaipur", "Rajasthan"), "जयपुर": ("Jaipur", "Rajasthan"),
    "chennai": ("Chennai", "Tamil Nadu"),
    "bangalore": ("Bengaluru", "Karnataka"), "bengaluru": ("Bengaluru", "Karnataka"),
    "kolkata": ("Kolkata", "West Bengal"),
}


def _find_gazetteer_hits(text: str) -> list:
    """Returns [(canonical_district, state, match_start), ...] for every
    gazetteer alias found in text, matched case-insensitively."""
    hits = []
    if not text:
        return hits
    text_lower = text.lower()
    for alias, (canonical, state) in _DISTRICT_STATE_GAZETTEER.items():
        for m in re.finditer(re.escape(alias.lower()), text_lower):
            hits.append((canonical, state, m.start()))
    hits.sort(key=lambda h: h[2])
    return hits


def extract_injured_home_location(ocr_text: str) -> Optional[dict]:
    """
    Looks for the injured person's residence district/state -- searches in
    a window AFTER residence-indicating keywords (R/o, निवासी, District,
    जिला) rather than trying to match the whole address string, since OCR
    noise makes full-address matching unreliable. Falls back to the first
    gazetteer hit in the document's opening block (cause-title / party
    description usually appears within the first ~20%).
    """
    if not ocr_text:
        return None
    residence_keywords = [r'r/o', r'निवासी', r'resident of', r'district\s*:', r'जिला']
    for kw in residence_keywords:
        for m in re.finditer(kw, ocr_text, re.IGNORECASE):
            window = ocr_text[m.start():m.start() + 200]
            hits = _find_gazetteer_hits(window)
            if hits:
                canonical, state, _ = hits[0]
                return {"district": canonical, "state": state, "context": window.strip()[:120]}
    head_text = ocr_text[: max(2000, int(len(ocr_text) * 0.2))]
    hits = _find_gazetteer_hits(head_text)
    if hits:
        canonical, state, _ = hits[0]
        return {"district": canonical, "state": state, "context": None}
    return None


def extract_hospital_locations(ocr_text: str) -> list:
    """
    Finds every district/state mentioned near a hospital/treatment keyword
    (अस्पताल, Hospital, भर्ती, admitted, referred, discharge). Returns a
    de-duplicated list of {"district", "state", "context"}.
    """
    if not ocr_text:
        return []
    treatment_keywords = [
        r'अस्पताल', r'hospital', r'भर्ती', r'admitted', r'referred', r'रेफर',
        r'discharge', r'डिस्चार्ज',
    ]
    found = []
    seen = set()
    for kw in treatment_keywords:
        for m in re.finditer(kw, ocr_text, re.IGNORECASE):
            start = max(0, m.start() - 100)
            window = ocr_text[start:m.start() + 100]
            for canonical, state, _ in _find_gazetteer_hits(window):
                key = (canonical, state)
                if key not in seen:
                    seen.add(key)
                    found.append({"district": canonical, "state": state, "context": window.strip()[:150]})
    return found


def check_treatment_location_mismatch(ocr_text: str, injury_headwise_table: dict) -> dict:
    """
    If the injured person was treated in a different district/state than
    their home district/state, that supports Transportation and Attender
    Charges as expected heads. Cross-checks against what the tribunal
    actually awarded for those two heads and flags a likely-missed or
    under-awarded head if they're zero/unitemized despite the mismatch.
    """
    home = extract_injured_home_location(ocr_text)
    hospitals = extract_hospital_locations(ocr_text)

    if not home or not hospitals:
        return {
            "checked": False,
            "reason": "Could not confidently identify both a home district and a treatment-location district from the OCR text.",
        }

    mismatches = [
        h for h in hospitals
        if (h["district"], h["state"]) != (home["district"], home["state"])
    ]

    if not mismatches:
        return {
            "checked": True,
            "mismatch": False,
            "home": home,
            "note": "Treatment location(s) match the injured person's home district/state — no travel-based justification expected for Transportation/Attender beyond local norms.",
        }

    transport_awarded = injury_headwise_table.get("transportation")
    attender_awarded = injury_headwise_table.get("attender_charges")

    flagged = []
    if not transport_awarded:
        flagged.append("Transportation")
    if not attender_awarded:
        flagged.append("Attender Charges")

    travel_desc = ", ".join(f"{m['district']}, {m['state']}" for m in mismatches)
    if flagged:
        note = (
            f"Treated at {travel_desc} — different district/state from home "
            f"({home['district']}, {home['state']}). {' and '.join(flagged)} "
            f"awarded as zero/not itemized despite this out-of-district travel — "
            f"likely missed or under-awarded head(s)."
        )
    else:
        note = (
            f"Treated at {travel_desc} — different district/state from home "
            f"({home['district']}, {home['state']}), and Transportation/Attender "
            f"Charges were awarded, consistent with the travel required."
        )

    return {
        "checked": True,
        "mismatch": True,
        "home": home,
        "treatment_locations": mismatches,
        "flagged_heads": flagged,
        "note": note,
    }


# ──────────────────────────────────────────────────────────────────────────
# TOP-LEVEL ENTRYPOINT
# ──────────────────────────────────────────────────────────────────────────
def build_justification(parsed_fields: dict | None, calculator_result: dict | None, ocr_text: str | None) -> dict:
    """
    Runs Steps 0-4 and returns STRUCTURED data (never prose):

    {
      "status": "ok" | "insufficient_data",
      "case_type": "death" | "injury",
      "tribunal_total": float,
      "tribunal_total_source": str,
      "tribunal_total_confidence": "high" | "medium" | "low",
      "calculator_total": float,
      "calculator_breakdown": {...full calculator output...},
      "diff": float,
      "math_relation": "equal" | "tribunal_lower" | "tribunal_higher",
      "headwise_comparison": [ {head, calculator_amount, tribunal_amount, verdict}, ... ],
      "field_sources": {field_name: "form" | "ocr_reparse" | "unresolved"},
      "hypothesis_grid": {...}         # death cases only
      "formula_analysis": {...}        # injury cases only
    }
    """
    pf = dict(parsed_fields or {})
    cr = calculator_result or {}

    # Fold in the itemised pecuniary-head values (medical expenses, pain & suffering,
    # transportation, attender charges, consortium, etc.) from the calculator that has
    # ALREADY been run on the frontend, when those fields are missing from
    # parsed_fields. parsed_fields only carries the top-level inputs (age/income/
    # disability/dependents/marital_status); the itemised heads live on
    # calculator_result. Without this fold-in, Step 2 recomputes calc_total from an
    # incomplete field set and can land on Rs. 0 even though the user has already run
    # the calculator and is looking at a real, non-zero total on screen -- producing a
    # contradictory verdict (e.g. "OVER/UNDER-COMPENSATED vs. a calculator estimate of
    # Rs. 0" right after the on-screen calculator showed a matching, non-zero total).
    # This does NOT trust cr["final_amount"] directly -- Step 2 below still always
    # recomputes the total from these per-field inputs server-side.
    _carry_over_fields = (
        "medical_expenses", "future_medical_expenses", "pain_and_suffering",
        "transportation", "special_diet", "attender_charges", "loss_of_income",
        "consortium", "funeral_expenses", "loss_estate",
    )
    for _f in _carry_over_fields:
        if _is_blank(pf.get(_f)) and not _is_blank(cr.get(_f)):
            pf[_f] = cr.get(_f)

    case_type_hint = str(pf.get("case_type") or cr.get("case_type") or "").strip().lower() or None

    # STEP 0
    resolved_fields, field_sources, reparsed_case_type = resolve_case_data(pf, ocr_text, case_type_hint)

    case_type = case_type_hint or reparsed_case_type or "injury"
    if case_type not in ("death", "injury"):
        case_type = "injury"

    if not ocr_text or not ocr_text.strip():
        # Step 0 fallback #3 -- no PDF loaded at all, don't guess.
        return {
            "status": "insufficient_data",
            "message": "Please upload the judgment PDF before requesting a justification.",
        }

    # STEP 1
    tribunal_result = resolve_tribunal_total(resolved_fields, ocr_text)
    tribunal_total = tribunal_result["value"]

    # STEP 2 -- always recomputed server-side
    calc_breakdown = resolve_calculator_total(resolved_fields, case_type)
    calc_total = calc_breakdown.get("final_amount", 0)

    # STEP 2b -- guard against a false "tribunal_higher" / OVER-COMPENSATED verdict
    # when calc_total is 0 only because the calculator inputs (age, income,
    # disability, medical expenses, pain & suffering, etc.) were never entered/
    # resolved for this case -- not because the calculator genuinely computed a
    # zero-value claim. Comparing a real tribunal award against an empty
    # calculator is a data-insufficiency case, not a quantum finding.
    _relevant_calc_fields = _INJURY_FIELDS if case_type == "injury" else _DEATH_FIELDS
    _has_any_calc_input = any(
        not _is_blank(resolved_fields.get(f)) and safe_float(resolved_fields.get(f), 0.0) != 0.0
        for f in _relevant_calc_fields
    )
    if (not calc_total or calc_total == 0) and not _has_any_calc_input:
        return {
            "status": "insufficient_data",
            "message": (
                "The calculator inputs for this case (age, income, disability, and the "
                "pecuniary heads such as medical expenses, pain & suffering, "
                "transportation, etc.) have not been entered on the workstation form, "
                "so the calculator total is Rs. 0 and cannot be meaningfully compared "
                "against the tribunal's award. Please fill in the calculator fields (or "
                "click Autofill) before requesting a quantum justification."
            ),
            "case_type": case_type,
            "tribunal_total": tribunal_total,
            "calculator_total": calc_total,
            "calculator_breakdown": calc_breakdown,
            "field_sources": field_sources,
        }

    if tribunal_total is None:
        return {
            "status": "insufficient_data",
            "message": "Could not determine the tribunal's awarded amount from this document (workstation field was blank, regex extraction found nothing, and the fallback AI extraction was unavailable or found nothing).",
            "case_type": case_type,
            "calculator_total": calc_total,
            "calculator_breakdown": calc_breakdown,
            "field_sources": field_sources,
        }

    diff = round(calc_total - tribunal_total, 2)
    if abs(diff) < 1:
        math_relation = "equal"
    elif diff > 0:
        math_relation = "tribunal_lower"
    else:
        math_relation = "tribunal_higher"

    # STEP 4 -- head-wise figures from the deterministic parser, not the LLM.
    # Death and injury cases use different parser functions because
    # extract_compensation_table_fields() only ever populates death-case
    # heads (consortium/funeral/estate) -- injury heads (medical/transport/
    # attender/etc.) come from the generic table parser + fuzzy head mapping.
    if case_type == "injury":
        tribunal_table_fields = extract_injury_headwise_table(ocr_text)
    else:
        tribunal_table_fields = extract_compensation_table_fields(ocr_text, case_type=case_type)
    headwise = build_headwise_comparison(case_type, calc_breakdown, tribunal_table_fields)

    result = {
        "status": "ok",
        "case_type": case_type,
        "tribunal_total": tribunal_total,
        "tribunal_total_source": tribunal_result["source"],
        "tribunal_total_confidence": tribunal_result["confidence"],
        "calculator_total": calc_total,
        "calculator_breakdown": calc_breakdown,
        "diff": diff,
        "math_relation": math_relation,
        "headwise_comparison": headwise,
        "field_sources": field_sources,
    }

    # STEP 3
    if case_type == "death":
        result["hypothesis_grid"] = run_death_hypothesis_grid(resolved_fields, tribunal_total)
    else:
        tribunal_future_loss = tribunal_table_fields.get("annual_loss_dependency")
        result["formula_analysis"] = solve_injury_formula(resolved_fields, ocr_text, tribunal_future_loss)
        # STEP 5 -- treatment-location vs. residence mismatch (injury only)
        result["treatment_location_check"] = check_treatment_location_mismatch(ocr_text, tribunal_table_fields)

    return result
