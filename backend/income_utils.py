import re
import logging

logger = logging.getLogger("IncomeUtils")

# Strong indicators (can stand alone as indicators of the period)
STRONG_ANNUAL_KEYWORDS = ["per annum", "p.a.", "per year", "annum", "वार्षिक"]
STRONG_MONTHLY_KEYWORDS = ["p.m.", "per month", "प्रतिमाह", "प्रति माह"]

# Weak indicators (only indicate period if they co-occur with an income context word)
WEAK_ANNUAL_KEYWORDS = ["annual", "yearly", "year", "सालाना"]
WEAK_MONTHLY_KEYWORDS = ["monthly", "month", "मासिक"]

# Income context indicators
INCOME_KEYWORDS = ["income", "salary", "earnings", "wage", "notional", "pay", "वेतन", "आय", "कमाई"]

def normalize_income_to_monthly(value: float, context_text: str, source: str, explicit_period: str = None) -> dict:
    """
    Standardizes a raw income value to a monthly amount based on context clues or an explicit override.
    
    Args:
        value (float): The raw numerical income value extracted.
        context_text (str): The text surrounding the value to check for period indicators.
        source (str): Identifier of the caller source (for tracing and custom log messages).
        explicit_period (str): If provided, overrides the keyword search and sets the period directly ("annual" or "monthly").
        
    Returns:
        dict:
            - "monthly_income": float (rounded to 2 decimal places if converted, otherwise unchanged)
            - "income_period": str ("annual", "monthly", or "ambiguous")
            - "method": str (description of how it was determined)
            - "confidence": dict (containing "confidence" float and "reason" string)
    """
    if value is None or value <= 0:
        return {
            "monthly_income": None,
            "income_period": "ambiguous",
            "method": f"Invalid value ({source})",
            "confidence": {"confidence": 0.0, "reason": "No valid value"}
        }

    if explicit_period in ("annual", "monthly"):
        is_annual = (explicit_period == "annual")
        is_monthly = (explicit_period == "monthly")
    else:
        context_lower = context_text.lower()
        
        # 1. Check strong indicators first
        is_annual = False
        for kw in STRONG_ANNUAL_KEYWORDS:
            if kw == "p.a.":
                if "p.a." in context_lower or "pa" in re.split(r'\W+', context_lower):
                    is_annual = True
                    break
            elif re.search(rf"\b{re.escape(kw)}\b", context_lower):
                is_annual = True
                break
                
        is_monthly = False
        for kw in STRONG_MONTHLY_KEYWORDS:
            if kw == "p.m.":
                if "p.m." in context_lower or "pm" in re.split(r'\W+', context_lower):
                    is_monthly = True
                    break
            elif re.search(rf"\b{re.escape(kw)}\b", context_lower):
                is_monthly = True
                break

        # 2. Check weak indicators with income context check (without short-circuiting check of the other type)
        has_income_context = any(kw in context_lower for kw in INCOME_KEYWORDS)
        
        if not is_annual and has_income_context:
            for kw in WEAK_ANNUAL_KEYWORDS:
                if re.search(rf"\b{re.escape(kw)}\b", context_lower):
                    is_annual = True
                    break
                    
        if not is_monthly and has_income_context:
            for kw in WEAK_MONTHLY_KEYWORDS:
                if re.search(rf"\b{re.escape(kw)}\b", context_lower):
                    is_monthly = True
                    break

    # Determine period and normalize
    if is_annual and not is_monthly:
        normalized = round(value / 12.0, 2)
        period = "annual"
        if source == "Compensation Table Extraction":
            method = "Compensation Table Extraction (Annual->Monthly)"
        else:
            method = f"Normalized from annual to monthly ({source})"
        confidence = {
            "confidence": 0.85,
            "reason": "Converted from annual income to monthly"
        }
    elif is_monthly and not is_annual:
        normalized = value
        period = "monthly"
        if source == "Compensation Table Extraction":
            method = "Compensation Table Extraction"
        else:
            method = f"Confirmed monthly income ({source})"
        confidence = {
            "confidence": 0.95,
            "reason": "Confirmed monthly income"
        }
    elif is_annual and is_monthly:
        # Both are mentioned, keep as-is but flag lower confidence
        normalized = value
        period = "ambiguous"
        method = f"Conflicting period indicators in context ({source})"
        confidence = {
            "confidence": 0.50,
            "reason": "Both monthly and annual keywords detected in context window"
        }
    else:
        # Ambiguous case: neither monthly nor annual specified
        normalized = value
        period = "ambiguous"
        method = f"Ambiguous income period ({source})"
        confidence = {
            "confidence": 0.40,
            "reason": f"No explicit period keyword found in context window: {source}"
        }
        
    return {
        "monthly_income": normalized,
        "income_period": period,
        "method": method,
        "confidence": confidence
    }
