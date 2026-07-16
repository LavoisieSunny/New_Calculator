import logging
from typing import Any, Optional
from datetime import date, datetime
from fastapi import APIRouter
from pydantic import BaseModel, model_validator

logger = logging.getLogger("backend.calculator")
router = APIRouter()

def get_conventional_heads_enhanced(base_amount: float, reference_date: date, anchor_date: date = date(2017, 10, 31)) -> float:
    if reference_date <= anchor_date:
        return float(base_amount)
    years_elapsed = reference_date.year - anchor_date.year
    if (reference_date.month, reference_date.day) < (anchor_date.month, anchor_date.day):
        years_elapsed -= 1
    periods = years_elapsed // 3
    return float(round(base_amount * (1.10 ** periods), 2))

# ======================================================
# SAFE NUMERIC PARSING HELPERS (Task 4)
# ======================================================

def safe_float(val, default=0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

def safe_int(val, default=0) -> int:
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

# ======================================================
# REQUEST MODEL
# ======================================================

class CompensationRequest(BaseModel):

    # ==================================================
    # COMMON
    # ==================================================

    case_type: str = "injury"

    age: int = 30

    monthly_income: float = 0.0

    award_date: Optional[str] = None
    date_of_accident: Optional[str] = None

    # ==================================================
    # DEATH CASE
    # ==================================================

    dependents: int = 0

    marital_status: str = "married"

    future_type: int = 2

    future_prospect: Optional[float] = None

    consortium: Optional[float] = None

    funeral_expenses: Optional[float] = None

    loss_estate: Optional[float] = None

    # Consortium Breakdown Subheadings (from PHP claim calculator)
    conlum: float = 0.0
    conspo: float = 0.0
    conpar: float = 0.0
    conchil: float = 0.0
    conwif: float = 0.0
    conmo: float = 0.0
    confath: float = 0.0
    conhus: float = 0.0
    conbro: float = 0.0
    consis: float = 0.0

    # ==================================================
    # INJURY CASE
    # ==================================================

    disability: float = 0.0

    medical_expenses: float = 0.0

    future_medical_expenses: float = 0.0

    pain_and_suffering: float = 0.0

    transportation: float = 0.0

    special_diet: float = 0.0

    attender_charges: float = 0.0

    loss_of_income: float = 0.0

    # Additional pecuniary/non-pecuniary heads (from PHP claim calculator)
    coliti: float = 0.0
    misex: float = 0.0
    loamiti: float = 0.0
    lopmarri: float = 0.0
    loexlife: float = 0.0
    loveaff: float = 0.0
    lossofenjoy: float = 0.0

    @model_validator(mode='before')
    @classmethod
    def clean_empty_strings(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        
        cleaned = {}
        for k, v in data.items():
            # If the value is empty string, string 'null', string 'NaN', or None
            if v == "" or v == "NaN" or v == "null" or v is None:
                # Provide safe defaults if the value is empty
                if k == "case_type":
                    cleaned[k] = "injury"
                elif k == "marital_status":
                    cleaned[k] = "married"
                elif k in ["age", "future_type"]:
                    cleaned[k] = 30 if k == "age" else 2
                elif k == "future_prospect":
                    cleaned[k] = None
                elif k in ["monthly_income", "consortium", "funeral_expenses", "loss_estate", "disability"]:
                    if k in ["consortium", "funeral_expenses", "loss_estate"]:
                        cleaned[k] = None
                    else:
                        cleaned[k] = 0.0
                else:
                    cleaned[k] = 0.0 if k in [
                        "medical_expenses", "future_medical_expenses", "pain_and_suffering",
                        "transportation", "special_diet", "attender_charges", "loss_of_income",
                        "conlum", "conspo", "conpar", "conchil", "conwif", "conmo", "confath",
                        "conhus", "conbro", "consis", "coliti", "misex", "loamiti", "lopmarri",
                        "loexlife", "loveaff", "lossofenjoy"
                    ] else 0
            else:
                # Coerce numeric values if passed as string but non-empty
                if k in ["age", "dependents", "future_type"]:
                    cleaned[k] = safe_int(v)
                elif k in [
                    "monthly_income", "consortium", "funeral_expenses", "loss_estate", "disability",
                    "medical_expenses", "future_medical_expenses", "pain_and_suffering",
                    "transportation", "special_diet", "attender_charges", "loss_of_income",
                    "conlum", "conspo", "conpar", "conchil", "conwif", "conmo", "confath",
                    "conhus", "conbro", "consis", "coliti", "misex", "loamiti", "lopmarri",
                    "loexlife", "loveaff", "lossofenjoy", "future_prospect"
                ]:
                    if k == "future_prospect":
                        cleaned[k] = safe_float(v) if v is not None and v != "" else None
                    else:
                        cleaned[k] = safe_float(v)
                else:
                    cleaned[k] = v
        return cleaned


# ======================================================
# SARLA VERMA MULTIPLIER
# ======================================================

def get_multiplier(age: int):

    if age <= 15:
        return 15  # Corrected to match MPHC PHP formula exactly

    elif age <= 20:
        return 18

    elif age <= 25:
        return 18

    elif age <= 30:
        return 17

    elif age <= 35:
        return 16

    elif age <= 40:
        return 15

    elif age <= 45:
        return 14

    elif age <= 50:
        return 13

    elif age <= 55:
        return 11

    elif age <= 60:
        return 9

    elif age <= 65:
        return 7

    return 5


# ======================================================
# FUTURE PROSPECTS
# ======================================================

def get_future_prospect(age: int, future_type: int):
    """
    Future prospects addition per National Insurance Co. Ltd. v. Pranay Sethi,
    (2017) 16 SCC 680, para 59.3/59.4 -- percentage depends on the deceased's
    AGE, not a flat rate.
    """
    if future_type == 1:  # permanent job
        if age < 40:
            return 0.50
        elif age < 50:
            return 0.30
        elif age < 60:
            return 0.15
        return 0.0
    else:  # self-employed / fixed salary / daily wage
        if age < 40:
            return 0.40
        elif age < 50:
            return 0.25
        elif age < 60:
            return 0.10
        return 0.0


# ======================================================
# DEDUCTION
# ======================================================

def get_deduction(
    dependents: int,
    marital_status: str
):
    """
    Deduction towards personal & living expenses (Sarla Verma / Pranay Sethi table).

    Business rule (matches the corrected PHP calculator):
      - Bachelor/Single: the UI never asks for "Number of Dependents" at all.
        Deduction is ALWAYS 1/2, regardless of whatever value is sent.
      - Married: counts total family size including the deceased (family_size = dependents + 1).
        Under Sarla Verma:
          - 2 to 3 family members (dependents <= 2) -> 1/3
          - 4 to 6 family members (dependents <= 5) -> 1/4 (0.25)
          - 7 or more family members (dependents >= 6) -> 1/5 (0.20)
    """
    if not marital_status:
        marital_status = "married"

    dependents = safe_int(dependents, 0)

    # Normalise bachelor/single variants — PHP sends 'B'
    is_bachelor = marital_status.strip().upper() in ("B", "BACHELOR", "SINGLE", "UNMARRIED", "S")

    if is_bachelor:
        return 0.50
    else:
        # Married (shifted by 1 for family size including deceased)
        if dependents <= 2:
            return 1 / 3
        elif dependents <= 5:
            return 0.25
        else:
            return 0.20


# ======================================================
# DEATH CASE CALCULATION
# ======================================================

def calculate_death_compensation(
    data: CompensationRequest
):
    age = safe_int(data.age, 30)
    monthly_income = safe_float(data.monthly_income, 0.0)
    dependents = safe_int(data.dependents, 0)
    marital_status = data.marital_status or "married"
    future_type = safe_int(data.future_type, 2)

    multiplier = get_multiplier(age)
    if data.future_prospect is not None:
        future_prospect_percentage = round(safe_float(data.future_prospect))
    else:
        future_percent = get_future_prospect(age, future_type)
        future_prospect_percentage = round(future_percent * 100)

    future_prospect_amount_float = monthly_income * future_prospect_percentage / 100.0
    enhanced_monthly_income_float = monthly_income + future_prospect_amount_float
    annual_income_float = enhanced_monthly_income_float * 12.0

    deduction_ratio = get_deduction(dependents, marital_status)
    # Express as a readable fraction label matching PHP output (1/2, 1/3, 1/4, 1/5)
    _frac_map = {0.50: "1/2", round(1/3, 10): "1/3", 0.25: "1/4", 0.20: "1/5"}
    deduction_label = _frac_map.get(round(deduction_ratio, 10), str(round(deduction_ratio, 4)))
    deduction_percentage = round(deduction_ratio * 100)
    
    deduction_amount_float = annual_income_float * deduction_ratio
    dependency_income_float = annual_income_float - deduction_amount_float
    loss_of_dependency_float = dependency_income_float * multiplier

    # Determine reference date for conventional heads escalation
    ref_date = None
    if data.award_date:
        for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                ref_date = datetime.strptime(data.award_date.strip(), fmt).date()
                break
            except ValueError:
                continue

    if not ref_date and data.date_of_accident:
        for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                ref_date = datetime.strptime(data.date_of_accident.strip(), fmt).date()
                break
            except ValueError:
                continue

    if not ref_date:
        logger.warning("No reliable award_date or date_of_accident available. Falling back to today's date.")
        ref_date = date.today()

    consortium_default = get_conventional_heads_enhanced(40000.0, ref_date)
    funeral_default = get_conventional_heads_enhanced(15000.0, ref_date)
    loss_estate_default = get_conventional_heads_enhanced(15000.0, ref_date)

    consortium = safe_float(data.consortium, consortium_default) if data.consortium is not None else consortium_default
    funeral_expenses = safe_float(data.funeral_expenses, funeral_default) if data.funeral_expenses is not None else funeral_default
    loss_estate = safe_float(data.loss_estate, loss_estate_default) if data.loss_estate is not None else loss_estate_default

    # Consortium breakdown sub-heads (Pranay Sethi / Nanu Ram style)
    # Each is a separate user-entered per-person value, added independently per PHP line 351
    conlum  = safe_float(data.conlum, 0.0)
    conspo  = safe_float(data.conspo, 0.0)
    conpar  = safe_float(data.conpar, 0.0)
    conchil = safe_float(data.conchil, 0.0)
    conwif  = safe_float(data.conwif, 0.0)
    conmo   = safe_float(data.conmo, 0.0)
    confath = safe_float(data.confath, 0.0)
    conhus  = safe_float(data.conhus, 0.0)
    conbro  = safe_float(data.conbro, 0.0)
    consis  = safe_float(data.consis, 0.0)

    consortium_breakdown_total = (
        conlum + conspo + conpar + conchil + conwif +
        conmo + confath + conhus + conbro + consis
    )

    # 1. Consortium double-counting fix:
    # If the user enters specific breakdown fields (consortium breakdown > 0),
    # the breakdown replaces/overrides the generic consortium amount.
    if consortium_breakdown_total > 0.0:
        consortium = 0.0

    final_compensation = (
        loss_of_dependency_float +
        consortium +
        funeral_expenses +
        loss_estate +
        consortium_breakdown_total
    )

    return {
        "case_type": "death",
        "monthly_income": round(monthly_income),
        "future_prospect_percentage": future_prospect_percentage,
        "future_prospect_amount": round(future_prospect_amount_float),
        "enhanced_monthly_income": round(enhanced_monthly_income_float),
        "annual_income": round(annual_income_float),
        "future_income": round(annual_income_float),
        "deduction_percentage": deduction_percentage,
        "deduction_label": deduction_label,
        "deduction_amount": round(deduction_amount_float),
        "dependency_income": round(dependency_income_float),
        "multiplier": multiplier,
        "loss_of_dependency": round(loss_of_dependency_float),
        "consortium": consortium,
        "funeral_expenses": funeral_expenses,
        "loss_estate": loss_estate,
        "conlum": conlum, "conspo": conspo, "conpar": conpar,
        "conchil": conchil, "conwif": conwif, "conmo": conmo,
        "confath": confath, "conhus": conhus, "conbro": conbro, "consis": consis,
        "consortium_breakdown_total": round(consortium_breakdown_total),
        "final_compensation": round(final_compensation),
        "final_amount": round(final_compensation)
    }




# ======================================================
# INJURY CASE CALCULATION
# ======================================================

def calculate_injury_compensation(
    data: CompensationRequest
):
    age = safe_int(data.age, 30)
    monthly_income = safe_float(data.monthly_income, 0.0)
    disability = safe_float(data.disability, 0.0)

    multiplier = get_multiplier(age)
    annual_income = monthly_income * 12
    future_income_loss = annual_income * (disability / 100.0) * multiplier

    medical_expenses = safe_float(data.medical_expenses, 0.0)
    future_medical_expenses = safe_float(data.future_medical_expenses, 0.0)
    pain_and_suffering = safe_float(data.pain_and_suffering, 0.0)
    transportation = safe_float(data.transportation, 0.0)
    special_diet = safe_float(data.special_diet, 0.0)
    attender_charges = safe_float(data.attender_charges, 0.0)
    loss_of_income = safe_float(data.loss_of_income, 0.0)

    coliti = safe_float(data.coliti, 0.0)
    misex = safe_float(data.misex, 0.0)
    loamiti = safe_float(data.loamiti, 0.0)
    lopmarri = safe_float(data.lopmarri, 0.0)
    loexlife = safe_float(data.loexlife, 0.0)
    loveaff = safe_float(data.loveaff, 0.0)
    lossofenjoy = safe_float(data.lossofenjoy, 0.0)

    final_amount = (
        future_income_loss +
        medical_expenses +
        future_medical_expenses +
        pain_and_suffering +
        transportation +
        special_diet +
        attender_charges +
        loss_of_income +
        coliti +
        misex +
        loamiti +
        lopmarri +
        loexlife +
        loveaff +
        lossofenjoy
    )

    return {
        "case_type": "injury",
        "multiplier": multiplier,
        "annual_income": round(annual_income),
        "future_income_loss": round(future_income_loss),
        "medical_expenses": medical_expenses,
        "future_medical_expenses": future_medical_expenses,
        "pain_and_suffering": pain_and_suffering,
        "transportation": transportation,
        "special_diet": special_diet,
        "attender_charges": attender_charges,
        "loss_of_income": loss_of_income,
        "coliti": coliti,
        "misex": misex,
        "loamiti": loamiti,
        "lopmarri": lopmarri,
        "loexlife": loexlife,
        "loveaff": loveaff,
        "lossofenjoy": lossofenjoy,
        "final_amount": round(final_amount),
    }


# ======================================================
# MAIN API
# ======================================================

@router.post("/")
async def calculate_compensation(
    data: CompensationRequest
):
    logger.info(f"Incoming calculation request payload: {data.dict() if data else 'None'}")
    try:
        case_type = str(data.case_type).strip().lower()
        logger.info(f"Parsed calculation case_type: {case_type}")
        
        if case_type == "death":
            breakdown = calculate_death_compensation(data)
        else:
            breakdown = calculate_injury_compensation(data)

        # Log formula inputs & parsed parameters as requested
        logger.info(f"Formula inputs & parsed parameters: {breakdown}")
        
        final_amount = breakdown.get("final_amount", 0)
        
        # Build standard Step 7 stable nested output schema
        response = {
            "success": True,
            "calculation_type": case_type,
            "total_compensation": final_amount,
            "breakdown": breakdown
        }
        # Merge breakdown keys into root for backwards compatibility with any flat-keyed expectations
        response.update(breakdown)

        logger.info(f"Successfully computed compensation. Total: {final_amount}")
        return response

    except Exception as e:
        logger.exception("CRITICAL EXCEPTION IN SERVER COMPENSATION CALCULATION PIPELINE:")
        # Return stable schema even on failures to prevent frontend crash
        return {
            "success": False,
            "calculation_type": data.case_type if data else "unknown",
            "total_compensation": 0,
            "breakdown": {},
            "error": str(e)
        }