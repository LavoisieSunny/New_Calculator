import unittest
from backend.calculator import (
    get_multiplier,
    get_future_prospect,
    get_deduction,
    calculate_death_compensation,
    CompensationRequest
)

class TestMPHCCalculator(unittest.TestCase):

    def test_mphc_death_compensation_validation_profile(self):
        """
        Verify the exact MPHC judicial example with simplified rules:
        - Monthly Income = 23,000
        - Future Prospects = 15% (Permanent job)
        - Dependents = 3 (deduction = 1/3)
        - Multiplier = 18 (age 25)
        - Conventional heads: consortium = 40,000, funeral = 15,000, estate = 15,000
        """
        # Age 25 yields a multiplier of 18
        # future_type 1 (permanent job) yields 15% prospects
        req = CompensationRequest(
            case_type="death",
            age=25,
            monthly_income=23000.0,
            dependents=3,
            marital_status="married",
            future_type=1,
            consortium=40000.0,
            funeral_expenses=15000.0,
            loss_estate=15000.0
        )
        
        res = calculate_death_compensation(req)
        
        # Verify step-by-step intermediate and final values against expectations
        self.assertEqual(res["future_prospect_percentage"], 15)
        self.assertEqual(res["future_prospect_amount"], 3450)
        self.assertEqual(res["enhanced_monthly_income"], 26450)
        self.assertEqual(res["annual_income"], 317400)
        self.assertEqual(res["deduction_percentage"], 33)
        self.assertEqual(res["deduction_amount"], 105800)
        self.assertEqual(res["dependency_income"], 211600)
        self.assertEqual(res["multiplier"], 18)
        self.assertEqual(res["loss_of_dependency"], 3808800)
        
        # Consortium: Now just 40000
        self.assertEqual(res["consortium"], 40000.0)
        # Final compensation: 3808800 + 40000 + 15000 + 15000 = 3878800
        self.assertEqual(res["final_compensation"], 3878800)
        self.assertEqual(res["final_amount"], 3878800)

        print("\n[SUCCESS] MPHC death compensation test passed with 100% mathematical precision!")
        print(f"  Enhanced Monthly Income: {res['enhanced_monthly_income']}")
        print(f"  Annual Income:           {res['annual_income']}")
        print(f"  Deduction Amount:        {res['deduction_amount']}")
        print(f"  Dependency Income:       {res['dependency_income']}")
        print(f"  Loss of Dependency:      {res['loss_of_dependency']}")
        print(f"  Final Settlement Value:  {res['final_compensation']}")

    def test_mphc_death_compensation_user_exact_validation(self):
        """
        Verify the exact user-specified validation test:
        - Age = 24 (Multiplier = 18)
        - Monthly Income = 23,000
        - Future Prospects Override = 50%
        - Dependents = 3 (Deduction = 1/3)
        - Loss Estate = 15,000, Consortium = 40,000, Funeral = 15,000
        """
        req = CompensationRequest(
            case_type="death",
            age=24,
            monthly_income=23000.0,
            dependents=3,
            marital_status="married",
            future_prospect=50.0,
            consortium=40000.0,
            funeral_expenses=15000.0,
            loss_estate=15000.0
        )
        
        res = calculate_death_compensation(req)
        
        # Verify the calculations
        self.assertEqual(res["future_prospect_percentage"], 50)
        self.assertEqual(res["future_prospect_amount"], 11500)
        self.assertEqual(res["enhanced_monthly_income"], 34500)
        self.assertEqual(res["annual_income"], 414000)
        self.assertEqual(res["deduction_amount"], 138000)
        self.assertEqual(res["dependency_income"], 276000)
        self.assertEqual(res["multiplier"], 18)
        self.assertEqual(res["loss_of_dependency"], 4968000)
        self.assertEqual(res["consortium"], 40000.0)
        self.assertEqual(res["final_compensation"], 5038000)
        self.assertEqual(res["final_amount"], 5038000)
        print("\n[SUCCESS] User exact validation test passed successfully! Output is 5,038,000.")

    def test_enhancement_and_claimants_multiplication(self):
        """
        Verify conventional heads are NOT multiplied by claimants/factors in the new logic:
        - Date of Accident: 2020
        - Dependents: 5
        - Consortium: 40000
        - Funeral Expenses: 15000
        - Loss of Estate: 15000
        """
        req = CompensationRequest(
            case_type="death",
            age=30,
            monthly_income=20000.0,
            dependents=5,
            marital_status="married",
            future_type=2,
            date_of_accident="2020-05-15",
            consortium=40000.0,
            funeral_expenses=15000.0,
            loss_estate=15000.0
        )
        res = calculate_death_compensation(req)
        self.assertEqual(res["consortium"], 40000.0)
        self.assertEqual(res["funeral_expenses"], 15000.0)
        self.assertEqual(res["loss_estate"], 15000.0)

    def test_multiplier_age_brackets(self):
        """
        Verify the multiplier boundaries:
        - Age < 15 -> 15
        - Age 15 to 25 -> 18
        - Age 26 to 30 -> 17
        - Age 31 to 35 -> 16
        - Age 36 to 40 -> 15
        - Age 41 to 45 -> 14
        - Age 46 to 50 -> 13
        - Age 51 to 55 -> 11
        - Age 56 to 60 -> 9
        """
        self.assertEqual(get_multiplier(14), 15)
        self.assertEqual(get_multiplier(15), 18)
        self.assertEqual(get_multiplier(20), 18)
        self.assertEqual(get_multiplier(25), 18)
        self.assertEqual(get_multiplier(30), 17)
        self.assertEqual(get_multiplier(35), 16)
        self.assertEqual(get_multiplier(40), 15)
        self.assertEqual(get_multiplier(45), 14)
        self.assertEqual(get_multiplier(50), 13)
        self.assertEqual(get_multiplier(51), 11)
        self.assertEqual(get_multiplier(55), 11)
        self.assertEqual(get_multiplier(56), 9)
        self.assertEqual(get_multiplier(60), 9)

if __name__ == "__main__":
    unittest.main()


class TestDeductionBracketFix(unittest.TestCase):
    """
    Regression tests for the missing '1 dependent' bracket bug
    (mirrors the fix applied to showcalreport_new_all_fresh.php).
    """

    def test_bachelor_always_gets_half_regardless_of_dependents(self):
        # Bachelor never asks for dependents - must always be 1/2, no matter what slips through
        self.assertEqual(get_deduction(0, "single"), 0.50)
        self.assertEqual(get_deduction(1, "bachelor"), 0.50)
        self.assertEqual(get_deduction(5, "B"), 0.50)   # even a stray high value -> still 1/2
        self.assertEqual(get_deduction("", "single"), 0.50)

    def test_married_with_one_dependent_no_longer_breaks(self):
        # Previously this fell through every bracket and silently returned an
        # undefined/incorrect ratio. It must now resolve to a sane default (1/3),
        # not the bachelor rate of 1/2.
        self.assertEqual(get_deduction(1, "married"), 1 / 3)
        self.assertEqual(get_deduction(0, "married"), 1 / 3)
        self.assertEqual(get_deduction("", "married"), 1 / 3)

    def test_married_brackets_unchanged(self):
        self.assertEqual(get_deduction(2, "married"), 1 / 3)
        self.assertEqual(get_deduction(3, "married"), 1 / 3)
        self.assertEqual(get_deduction(4, "married"), 0.25)
        self.assertEqual(get_deduction(6, "married"), 0.25)
        self.assertEqual(get_deduction(7, "married"), 0.20)

    def test_death_compensation_does_not_silently_zero_out_for_one_dependent(self):
        """
        End-to-end: a married death case with 1 dependent must still produce
        a real loss_of_dependency figure, not 0.
        """
        req = CompensationRequest(
            case_type="death",
            age=30,
            monthly_income=20000.0,
            dependents=1,
            marital_status="married",
            future_type=2,
        )
        res = calculate_death_compensation(req)
        self.assertGreater(res["loss_of_dependency"], 0)
        self.assertEqual(res["deduction_label"], "1/3")


if __name__ == "__main__":
    unittest.main()
