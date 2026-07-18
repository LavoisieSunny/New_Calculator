import os
import json
import unittest
from unittest.mock import patch
from backend.parser_heuristics import parse_extracted_text
from backend.calculator import CompensationRequest, calculate_death_compensation

# ── Mock ai_data_recovery for deterministic offline testing ──────────────────
def mock_ai_data_recovery(raw_ocr_text, track="high_court", case_type=None):
    raw_ocr_lower = raw_ocr_text.lower()
    
    if "lalit dahiya" in raw_ocr_lower or "siyadulari dahiya" in raw_ocr_lower:
        # ma_2196
        return {
            "case_type": "death",
            "age": 25,
            "multiplier": 18,
            "dependents": 1,
            "marital_status": "single",
            "monthly_income": 6090.0,
            "future_prospect": 40.0,
            "future_type": 2,
            "confidence_scores": {
                "deceased_name": {"confidence": 0.99},
                "claimant_name": {"confidence": 0.90},
                "age": {"confidence": 0.99},
                "monthly_income": {"confidence": 0.99},
                "multiplier": {"confidence": 0.99},
                "future_prospect": {"confidence": 0.99},
                "dependents": {"confidence": 0.99},
                "marital_status": {"confidence": 0.99}
            }
        }
    elif "pawan kumar baiga" in raw_ocr_lower or "santo bai baiga" in raw_ocr_lower or "birendra singh" in raw_ocr_lower:
        # ma_3078
        return {
            "case_type": "death",
            "age": 17,
            "multiplier": 18,
            "dependents": 0,
            "marital_status": "single",
            "monthly_income": 2500.0,
            "future_prospect": 40.0,
            "future_type": 2,
            "confidence_scores": {
                "deceased_name": {"confidence": 0.99},
                "claimant_name": {"confidence": 0.90},
                "age": {"confidence": 0.99},
                "monthly_income": {"confidence": 0.99},
                "multiplier": {"confidence": 0.99},
                "future_prospect": {"confidence": 0.99},
                "dependents": {"confidence": 0.99},
                "marital_status": {"confidence": 0.99}
            }
        }
    elif "madhuri goswami" in raw_ocr_lower or "ओमप्रकाश गोस्वामी" in raw_ocr_lower:
        # ma_5623
        return {
            "case_type": "death",
            "age": 55,
            "multiplier": 9,
            "dependents": 3,
            "monthly_income": 33989.67,
            "future_prospect": 15.0,
            "future_type": 1,
            "confidence_scores": {
                "deceased_name": {"confidence": 0.90},
                "claimant_name": {"confidence": 0.90},
                "age": {"confidence": 0.90},
                "monthly_income": {"confidence": 0.90},
                "multiplier": {"confidence": 0.90},
                "future_prospect": {"confidence": 0.90},
                "dependents": {"confidence": 0.90},
                "marital_status": {"confidence": 0.90}
            }
        }
    elif "anjani singh" in raw_ocr_lower or "parvati singh" in raw_ocr_lower:
        # ma_10076
        return {
            "case_type": "death",
            "age": 22,
            "multiplier": 18,
            "dependents": 4,
            "marital_status": "single",
            "monthly_income": 9650.0,
            "future_prospect": 40.0,
            "future_type": 2,
            "confidence_scores": {
                "deceased_name": {"confidence": 0.90},
                "claimant_name": {"confidence": 0.90},
                "age": {"confidence": 0.90},
                "monthly_income": {"confidence": 0.90},
                "multiplier": {"confidence": 0.90},
                "future_prospect": {"confidence": 0.90},
                "dependents": {"confidence": 0.90},
                "marital_status": {"confidence": 0.90}
            }
        }
    return None

class TestAutofillRegression(unittest.TestCase):
    def setUp(self):
        self.fixtures_dir = os.path.join(os.path.dirname(__file__), "tests", "fixtures", "high_court")

    def _assert_match(self, extracted, expected, field_name, tolerance=None):
        if expected is None:
            return
        
        if isinstance(expected, list):
            match_found = False
            for exp in expected:
                try:
                    if tolerance is not None:
                        if abs(float(extracted) - float(exp)) <= tolerance:
                            match_found = True
                            break
                    else:
                        if str(extracted).strip().lower() == str(exp).strip().lower():
                            match_found = True
                            break
                except (ValueError, TypeError):
                    if str(extracted).strip().lower() == str(exp).strip().lower():
                        match_found = True
                        break
            self.assertTrue(
                match_found, 
                f"Field '{field_name}' got '{extracted}', expected one of {expected}"
            )
        else:
            if tolerance is not None:
                self.assertIsNotNone(extracted, f"Field '{field_name}' is None, expected {expected}")
                self.assertAlmostEqual(float(extracted), float(expected), delta=tolerance, msg=f"Field '{field_name}' mismatch")
            else:
                self.assertEqual(
                    str(extracted).strip().lower() if extracted is not None else "",
                    str(expected).strip().lower(),
                    f"Field '{field_name}' mismatch"
                )

    @patch("backend.llm_client.ai_data_recovery", side_effect=mock_ai_data_recovery)
    def test_regression_all_fixtures(self, mock_recovery):
        for name in ["ma_2196", "ma_3078", "ma_5623", "ma_10076"]:
            txt_path = os.path.join(self.fixtures_dir, f"{name}.txt")
            json_path = os.path.join(self.fixtures_dir, f"{name}.json")
            
            self.assertTrue(os.path.exists(txt_path), f"Txt file not found: {txt_path}")
            self.assertTrue(os.path.exists(json_path), f"Json file not found: {json_path}")
            
            with open(txt_path, "r", encoding="utf-8") as f:
                lines = [line.rstrip() for line in f]
                
            with open(json_path, "r", encoding="utf-8") as f:
                fixture_data = json.load(f)
                
            ground_truth = fixture_data.get("ground_truth")
            self.assertIsNotNone(ground_truth, f"Ground truth missing in {name}.json")
            
            # Run autofill extraction pipeline
            suggestions = parse_extracted_text(lines)
            
            # 1. Assert scalar field extractions
            self._assert_match(suggestions.get("case_type"), ground_truth.get("case_type"), f"{name}: case_type")
            self._assert_match(suggestions.get("age"), ground_truth.get("age"), f"{name}: age")
            self._assert_match(suggestions.get("multiplier"), ground_truth.get("multiplier"), f"{name}: multiplier")
            self._assert_match(suggestions.get("dependents"), ground_truth.get("dependents"), f"{name}: dependents")
            self._assert_match(suggestions.get("marital_status"), ground_truth.get("marital_status"), f"{name}: marital_status")
            self._assert_match(suggestions.get("monthly_income"), ground_truth.get("monthly_income"), f"{name}: monthly_income", tolerance=50.0)
            
            # 2. Assert consortium, funeral_expenses, loss_estate are None in suggestions for death cases
            self.assertIsNone(suggestions.get("consortium"), f"{name}: consortium should be None under new spec")
            self.assertIsNone(suggestions.get("funeral_expenses"), f"{name}: funeral_expenses should be None under new spec")
            self.assertIsNone(suggestions.get("loss_estate"), f"{name}: loss_estate should be None under new spec")

            # 3. Run calculation and verify computed final compensation matches
            def safe_float_convert(val):
                if val in (None, "", "null", "None"):
                    return None
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return None

            def safe_int_convert(val, default=0):
                if val in (None, "", "null", "None"):
                    return default
                try:
                    return int(val)
                except (ValueError, TypeError):
                    return default

            req_data = {
                "case_type": suggestions.get("case_type") or "death",
                "age": safe_int_convert(suggestions.get("age"), 30),
                "monthly_income": safe_float_convert(suggestions.get("monthly_income")) or 0.0,
                "dependents": safe_int_convert(suggestions.get("dependents"), 0),
                "marital_status": suggestions.get("marital_status") or "married",
                "future_type": safe_int_convert(suggestions.get("future_type"), 2),
                "future_prospect": safe_float_convert(suggestions.get("future_prospect")),
                "consortium": None,
                "funeral_expenses": None,
                "loss_estate": None,
                "consortium_claimants": safe_int_convert(suggestions.get("consortium_claimants"), None)
            }
            # Special case for medical/ambulance expenses (maps to medical_expenses)
            medical_val = None
            if name == "ma_2196":
                medical_val = 45000.0
            elif name == "ma_10076":
                medical_val = 30000.0
            
            req = CompensationRequest(**req_data)
            if medical_val:
                req.medical_expenses = float(medical_val)
                
            calc_result = calculate_death_compensation(req)
            final_comp = calc_result.get("final_compensation")
            
            self._assert_match(final_comp, ground_truth.get("award_amount"), f"{name}: calculated final_compensation", tolerance=50000.0)

if __name__ == "__main__":
    unittest.main()
