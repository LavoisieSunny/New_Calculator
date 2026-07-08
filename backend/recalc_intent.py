"""
recalc_intent.py
Detects in-chat "what-if" recalculation requests (e.g. "disability is 40",
"what if age is 35", "recalculate with medical expenses 80000") and
computes the result deterministically using the SAME
calculate_injury_compensation / calculate_death_compensation functions
the main Calculate button uses, so the chatbot can never produce a number
that disagrees with the deterministic calculator, and always picks the
formula based on case_type (injury vs death). Plain factual questions
("what is the disability percentage in this case") are NOT treated as
recalculation and return None so they fall through to the normal
RAG+LLM path.
"""

import re
from typing import Optional, Tuple, Dict, Any

from backend.calculator import (
    CompensationRequest,
    calculate_injury_compensation,
    calculate_death_compensation,
    safe_float,
)

INJURY_FIELD_MAP = {
    "disability percentage": "disability", "disability percent": "disability",
    "disability perc": "disability", "disability %": "disability",
    "disability": "disability", "impairment": "disability",
    "victim age": "age", "claimant age": "age", "age": "age",
    "monthly income": "monthly_income", "income": "monthly_income",
    "salary": "monthly_income", "wages": "monthly_income",
    "future medical expenses": "future_medical_expenses", "future medical": "future_medical_expenses",
    "future treatment": "future_medical_expenses",
    "medical expenses": "medical_expenses", "medical": "medical_expenses",
    "treatment": "medical_expenses", "medical bills": "medical_expenses",
    "hospital bills": "medical_expenses",
    "pain and suffering": "pain_and_suffering", "pain suffering": "pain_and_suffering",
    "pain": "pain_and_suffering", "suffering": "pain_and_suffering",
    "transportation": "transportation", "transport": "transportation",
    "travel expenses": "transportation", "travel": "transportation",
    "special diet": "special_diet", "dietary expenses": "special_diet",
    "diet": "special_diet", "food": "special_diet",
    "attender charges": "attender_charges", "attendant": "attender_charges",
    "attender": "attender_charges", "nurse": "attender_charges", "caretaker": "attender_charges",
    "past income loss": "loss_of_income", "income loss": "loss_of_income",
    "loss of income": "loss_of_income",
}

DEATH_FIELD_MAP = {
    "victim age": "age", "claimant age": "age", "age": "age",
    "monthly income": "monthly_income", "income": "monthly_income",
    "salary": "monthly_income", "wages": "monthly_income",
    "number of dependents": "dependents", "no. of dependents": "dependents",
    "no of dependents": "dependents", "dependents": "dependents", "dependent": "dependents",
    "loss of consortium": "consortium", "consortium": "consortium",
    "funeral expenses": "funeral_expenses", "funeral costs": "funeral_expenses",
    "funeral": "funeral_expenses",
    "loss of estate": "loss_estate", "loss estate": "loss_estate", "estate": "loss_estate",
}

PERCENT_FIELDS = {"disability"}
COUNT_FIELDS = {"age", "dependents"}

INFORMATIONAL_STARTERS = (
    "what is", "what was", "what are", "how much", "how many", "why",
    "does the", "did the", "tell me about", "explain", "who ", "when ",
    "where ", "which ",
)

RECALC_TRIGGER_WORDS = (
    "recalculate", "re-calculate", "recompute", "re-compute",
    "what if", "revise", "what would", "if the", "suppose",
)

_ASSIGN_CUE = r"(?:is|=|:|to|as|at|of)?\s*₹?\s*([\d][\d,\.]*)"


def _looks_informational(lower_text: str) -> bool:
    if any(trig in lower_text for trig in RECALC_TRIGGER_WORDS):
        return False
    return lower_text.strip().startswith(INFORMATIONAL_STARTERS)


def parse_recalc_intent(text: str, case_type: str) -> Optional[Tuple[str, float, str]]:
    if not text:
        return None
    lower = text.lower().strip()
    if _looks_informational(lower):
        return None

    field_map = DEATH_FIELD_MAP if case_type == "death" else INJURY_FIELD_MAP
    keys = sorted(field_map.keys(), key=len, reverse=True)

    for phrase in keys:
        idx = lower.find(phrase)
        if idx == -1:
            continue
        tail = lower[idx + len(phrase): idx + len(phrase) + 20]
        m = re.match(r"\s*" + _ASSIGN_CUE, tail)
        if m:
            try:
                value = float(m.group(1).replace(",", ""))
            except ValueError:
                continue
            return field_map[phrase], value, phrase

    if any(trig in lower for trig in RECALC_TRIGGER_WORDS):
        nums = re.findall(r"[\d][\d,\.]*", lower)
        matched_fields = [phrase for phrase in keys if phrase in lower]
        if nums and len(matched_fields) == 1:
            try:
                value = float(nums[-1].replace(",", ""))
            except ValueError:
                return None
            return field_map[matched_fields[0]], value, matched_fields[0]

    return None


def build_recalc_base(parsed_fields: Dict[str, Any], calculator_result: Dict[str, Any], case_type: str) -> Dict[str, Any]:
    pf = parsed_fields or {}
    cr = calculator_result or {}

    base = {
        "case_type": case_type,
        "age": pf.get("age", 30),
        "monthly_income": pf.get("monthly_income", 0),
    }

    if case_type == "death":
        base.update({
            "dependents": pf.get("dependents", 0),
            "marital_status": pf.get("marital_status", "married"),
            "future_type": pf.get("future_type", 2),
            "consortium": cr.get("consortium", 40000),
            "funeral_expenses": cr.get("funeral_expenses", 15000),
            "loss_estate": cr.get("loss_estate", 15000),
        })
    else:
        base.update({
            "disability": pf.get("disability", 0),
            "medical_expenses": cr.get("medical_expenses", 0),
            "future_medical_expenses": cr.get("future_medical_expenses", 0),
            "pain_and_suffering": cr.get("pain_and_suffering", 0),
            "transportation": cr.get("transportation", 0),
            "special_diet": cr.get("special_diet", 0),
            "attender_charges": cr.get("attender_charges", 0),
            "loss_of_income": cr.get("loss_of_income", 0),
        })

    return base


def run_recalculation(question: str, parsed_fields: Optional[Dict[str, Any]], calculator_result: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    pf = parsed_fields or {}
    cr = calculator_result or {}
    case_type = str(pf.get("case_type") or cr.get("case_type") or "injury").lower()
    case_type = "death" if case_type == "death" else "injury"

    intent = parse_recalc_intent(question, case_type)
    if intent is None:
        return None

    field_key, value, matched_phrase = intent
    base = build_recalc_base(pf, cr, case_type)
    base[field_key] = value

    req = CompensationRequest(**base)
    breakdown = (
        calculate_death_compensation(req) if case_type == "death"
        else calculate_injury_compensation(req)
    )
    new_total = breakdown.get("final_amount", 0)
    tribunal_award = safe_float(pf.get("award_amount"), 0.0)

    if field_key in PERCENT_FIELDS:
        value_display = f"{value:,.0f}%"
    elif field_key in COUNT_FIELDS:
        value_display = f"{value:,.0f}"
    else:
        value_display = f"Rs. {value:,.0f}"

    lines = [
        f"**What-if recalculation** — {matched_phrase} = {value_display}",
        "",
        f"Using the **{case_type}** compensation formula (this case is a {case_type} claim, so the {case_type} formula is applied automatically):",
        "",
    ]

    if case_type == "death":
        rows = [
            ("Loss of Dependency", breakdown.get("loss_of_dependency")),
            ("Consortium", breakdown.get("consortium")),
            ("Funeral Expenses", breakdown.get("funeral_expenses")),
            ("Loss of Estate", breakdown.get("loss_estate")),
            ("Multiplier", breakdown.get("multiplier")),
            ("Future Prospect %", breakdown.get("future_prospect_percentage")),
            ("Deduction %", breakdown.get("deduction_percentage")),
        ]
    else:
        rows = [
            ("Future Income Loss", breakdown.get("future_income_loss")),
            ("Medical Expenses", breakdown.get("medical_expenses")),
            ("Future Medical Expenses", breakdown.get("future_medical_expenses")),
            ("Pain & Suffering", breakdown.get("pain_and_suffering")),
            ("Transportation", breakdown.get("transportation")),
            ("Special Diet", breakdown.get("special_diet")),
            ("Attender Charges", breakdown.get("attender_charges")),
            ("Loss of Income", breakdown.get("loss_of_income")),
            ("Multiplier", breakdown.get("multiplier")),
        ]

    for label, val in rows:
        if val in (None, 0, ""):
            continue
        if label == "Multiplier":
            lines.append(f"- {label}: {val}x")
        elif label in ("Future Prospect %", "Deduction %"):
            lines.append(f"- {label}: {val}%")
        else:
            lines.append(f"- {label}: Rs. {val:,.0f}")

    lines.append("")
    lines.append(f"**Revised Total: Rs. {new_total:,.0f}**")

    if tribunal_award > 0:
        diff = new_total - tribunal_award
        sign = "more than" if diff >= 0 else "less than"
        lines.append(f"Tribunal Award on record: Rs. {tribunal_award:,.0f} "
                      f"(revised estimate is Rs. {abs(diff):,.0f} {sign} the tribunal award).")

    return {
        "response": "\n".join(lines),
        "precedents": [],
        "recalculation": {
            "case_type": case_type,
            "changed_field": field_key,
            "changed_value": value,
            "breakdown": breakdown,
            "final_amount": new_total,
        },
    }
