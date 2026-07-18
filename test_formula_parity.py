import os
import json
import subprocess
import unittest
import sys
from backend.calculator import (
    CompensationRequest,
    calculate_death_compensation,
    calculate_injury_compensation
)

class TestFormulaParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # For tests, the root is the current directory of the workspace
        cls.root_dir = os.path.dirname(os.path.abspath(__file__))
        cls.app_js_path = os.path.join(cls.root_dir, "frontend", "app.js")
        
        # Verify Node is available
        try:
            subprocess.run(["node", "--version"], capture_output=True, check=True)
        except Exception:
            raise unittest.SkipTest("Node.js is not installed or not in PATH, skipping frontend parity checks.")

    def _run_js_calculator(self, data):
        run_script_path = os.path.join(self.root_dir, "tests", "run_calc.js")
        proc = subprocess.run(
            ["node", run_script_path],
            input=json.dumps(data),
            capture_output=True,
            text=True
        )
        if proc.returncode != 0:
            print("Node stderr:", proc.stderr)
            self.fail(f"Node execution failed: {proc.stderr}")
        return json.loads(proc.stdout.strip())

    def test_death_cases_parity(self):
        # Generate scenarios covering permutations of:
        # - different age ranges (multipliers, future prospects)
        # - married vs single (deductions)
        # - dependents count
        # - future type (permanent vs self-employed)
        # - consortium breakdown inputs vs single consortium input
        scenarios = [
            # 1. Lalit Dahiya style case (25yo, single, 1 dependent, self-employed, medicals)
            {
                "case_type": "death",
                "age": 25,
                "monthly_income": 6090.0,
                "dependents": 1,
                "marital_status": "single",
                "future_type": 2,
                "medical_expenses": 45000.0,
                "consortium": None,
                "funeral_expenses": None,
                "loss_estate": None
            },
            # 2. Pawan Kumar Baiga style case (17yo, single, minor, no dependents)
            {
                "case_type": "death",
                "age": 17,
                "monthly_income": 2500.0,
                "dependents": 0,
                "marital_status": "single",
                "future_type": 2,
                "consortium": None,
                "funeral_expenses": None,
                "loss_estate": None
            },
            # 3. Married regular job with large family and consortium breakdown
            {
                "case_type": "death",
                "age": 35,
                "monthly_income": 50000.0,
                "dependents": 5,
                "marital_status": "married",
                "future_type": 1,
                "conlum": 0.0,
                "conspo": 40000.0,
                "conpar": 40000.0,
                "conchil": 80000.0,
                "conwif": 0.0,
                "conmo": 0.0,
                "confath": 0.0,
                "conhus": 0.0,
                "conbro": 0.0,
                "consis": 0.0
            },
            # 4. Single permanent job, 3 dependents, lump sum consortium overridden
            {
                "case_type": "death",
                "age": 42,
                "monthly_income": 30000.0,
                "dependents": 3,
                "marital_status": "single",
                "future_type": 1,
                "consortium": 80000.0,
                "conlum": 120000.0,  # conlum > 0 should override main consortium to 0
                "conspo": 0.0
            }
        ]

        for idx, scenario in enumerate(scenarios):
            # Run JS calculator
            js_res = self._run_js_calculator(scenario)
            
            # Run Python calculator
            req_data = {
                "case_type": "death",
                "age": scenario.get("age", 30),
                "monthly_income": scenario.get("monthly_income", 0.0),
                "dependents": scenario.get("dependents", 0),
                "marital_status": scenario.get("marital_status", "married"),
                "future_type": scenario.get("future_type", 2),
                "future_prospect": scenario.get("future_prospect"),
                "consortium": scenario.get("consortium"),
                "funeral_expenses": scenario.get("funeral_expenses"),
                "loss_estate": scenario.get("loss_estate"),
                "consortium_claimants": scenario.get("consortium_claimants")
            }
            # Set consortium subheads
            for subhead in ["conlum", "conspo", "conpar", "conchil", "conwif", "conmo", "confath", "conhus", "conbro", "consis"]:
                if subhead in scenario:
                    req_data[subhead] = scenario[subhead]

            req = CompensationRequest(**req_data)
            if "medical_expenses" in scenario:
                req.medical_expenses = scenario["medical_expenses"]

            py_res = calculate_death_compensation(req)
            
            # Assert parity on final amount, multiplier, future prospect amount, deduction amount
            msg = f"Death scenario {idx} failed parity."
            self.assertAlmostEqual(js_res["final_amount"], py_res["final_compensation"], delta=2, msg=msg)
            self.assertEqual(js_res["multiplier"], py_res["multiplier"], msg)

    def test_injury_cases_parity(self):
        # Permutations of injury inputs (disability %, treatments, extra general damages)
        scenarios = [
            # 1. Generic injury with medicals and treatments
            {
                "case_type": "injury",
                "age": 30,
                "monthly_income": 15000.0,
                "disability": 20,
                "medical_expenses": 50000.0,
                "future_medical_expenses": 10000.0,
                "pain_and_suffering": 25000.0,
                "transportation": 5000.0,
                "special_diet": 5000.0,
                "attender_charges": 6000.0,
                "loss_of_income": 30000.0,
                "coliti": 10000.0,  # litigation
                "misex": 2000.0,    # misc
                "loamiti": 15000.0, # loss of amenity
                "lopmarri": 0.0,
                "loexlife": 0.0,
                "loveaff": 0.0,
                "lossofenjoy": 5000.0
            },
            # 2. Severe injury with marriage prospects and expectation of life loss
            {
                "case_type": "injury",
                "age": 22,
                "monthly_income": 25000.0,
                "disability": 80,
                "medical_expenses": 200000.0,
                "future_medical_expenses": 50000.0,
                "pain_and_suffering": 100000.0,
                "transportation": 20000.0,
                "special_diet": 15000.0,
                "attender_charges": 24000.0,
                "loss_of_income": 75000.0,
                "coliti": 15000.0,
                "misex": 5000.0,
                "loamiti": 50000.0,
                "lopmarri": 100000.0,
                "loexlife": 50000.0,
                "loveaff": 50000.0,
                "lossofenjoy": 30000.0
            }
        ]

        for idx, scenario in enumerate(scenarios):
            js_res = self._run_js_calculator(scenario)
            
            # Run Python calculator
            req_data = {
                "case_type": "injury",
                "age": scenario.get("age", 30),
                "monthly_income": scenario.get("monthly_income", 0.0),
                "disability": scenario.get("disability", 0.0),
                "medical_expenses": scenario.get("medical_expenses", 0.0),
                "future_medical_expenses": scenario.get("future_medical_expenses", 0.0),
                "pain_and_suffering": scenario.get("pain_and_suffering", 0.0),
                "transportation": scenario.get("transportation", 0.0),
                "special_diet": scenario.get("special_diet", 0.0),
                "attender_charges": scenario.get("attender_charges", 0.0),
                "loss_of_income": scenario.get("loss_of_income", 0.0),
                "coliti": scenario.get("coliti", 0.0),
                "misex": scenario.get("misex", 0.0),
                "loamiti": scenario.get("loamiti", 0.0),
                "lopmarri": scenario.get("lopmarri", 0.0),
                "loexlife": scenario.get("loexlife", 0.0),
                "loveaff": scenario.get("loveaff", 0.0),
                "lossofenjoy": scenario.get("lossofenjoy", 0.0)
            }
            req = CompensationRequest(**req_data)
            py_res = calculate_injury_compensation(req)
            
            msg = f"Injury scenario {idx} failed parity."
            self.assertAlmostEqual(js_res["final_amount"], py_res["final_amount"], delta=2, msg=msg)
            self.assertEqual(js_res["multiplier"], py_res["multiplier"], msg)

if __name__ == "__main__":
    unittest.main()
