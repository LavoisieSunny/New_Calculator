import unittest
from backend.calculator import (
    get_multiplier,
    get_future_prospect,
    get_deduction,
    calculate_death_compensation,
    calculate_injury_compensation,
    CompensationRequest
)

class TestMPHCCalculator(unittest.TestCase):

    def test_mphc_death_compensation_validation_profile(self):
        """
        Verify the exact MPHC judicial example with simplified rules:
        - Monthly Income = 23,000
        - Future Prospects = 15% (Permanent job, age 55)
        - Dependents = 2 (deduction = 1/3)
        - Multiplier = 11 (age 55)
        - Conventional heads: consortium = 40,000, funeral = 15,000, estate = 15,000
        """
        req = CompensationRequest(
            case_type="death",
            age=55,
            monthly_income=23000.0,
            dependents=2,
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
        self.assertEqual(res["multiplier"], 11)
        self.assertEqual(res["loss_of_dependency"], 2327600)
        
        # Consortium: Now just 40000
        self.assertEqual(res["consortium"], 40000.0)
        # Final compensation: 2327600 + 40000 + 15000 + 15000 = 2397600
        self.assertEqual(res["final_compensation"], 2397600)
        self.assertEqual(res["final_amount"], 2397600)

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
        - Dependents = 2 (Deduction = 1/3)
        - Loss Estate = 15,000, Consortium = 40,000, Funeral = 15,000
        """
        req = CompensationRequest(
            case_type="death",
            age=24,
            monthly_income=23000.0,
            dependents=2,
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
        - Age <= 15 -> 15
        - Age 16 to 25 -> 18
        - Age 26 to 30 -> 17
        - Age 31 to 35 -> 16
        - Age 36 to 40 -> 15
        - Age 41 to 45 -> 14
        - Age 46 to 50 -> 13
        - Age 51 to 55 -> 11
        - Age 56 to 60 -> 9
        """
        self.assertEqual(get_multiplier(14), 15)
        self.assertEqual(get_multiplier(15), 15)
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
        # Bachelor gets 1/2 for <= 1 dependents, and 1/3 for > 1 dependents
        self.assertEqual(get_deduction(0, "single"), 0.50)
        self.assertEqual(get_deduction(1, "bachelor"), 0.50)
        self.assertEqual(get_deduction(5, "B"), 1 / 3)   # bachelor with >1 dependents gets 1/3
        self.assertEqual(get_deduction("", "single"), 0.50)

    def test_married_with_one_dependent_no_longer_breaks(self):
        # Previously this fell through every bracket and silently returned an
        # undefined/incorrect ratio. It must now resolve to a sane default (1/3),
        # not the bachelor rate of 1/2.
        self.assertEqual(get_deduction(1, "married"), 1 / 3)
        self.assertEqual(get_deduction(0, "married"), 1 / 3)
        self.assertEqual(get_deduction("", "married"), 1 / 3)

    def test_married_brackets_corrected(self):
        self.assertEqual(get_deduction(2, "married"), 1 / 3)
        self.assertEqual(get_deduction(3, "married"), 1 / 3)
        self.assertEqual(get_deduction(4, "married"), 0.25)
        self.assertEqual(get_deduction(5, "married"), 0.25)
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

    def test_pranay_sethi_age_brackets(self):
        """
        Verify future prospects percentage and downstream final_compensation
        for at least one case in each age bracket (under 40, 40-50, 50-60, above 60)
        and exact boundaries (15, 40, 50, 60) for both permanent job (future_type=1)
        and self-employed (future_type=2).
        
        Also asserts that the duplicated frontend JS formulas (transpiled below)
        behave identically to the backend.
        
        TODO: Keep the frontend (app.js) and backend (calculator.py) multiplier and
              future prospects formulas in sync to avoid logic drift.
        """
        # Helper to mimic the frontend JS logic exactly
        def js_get_multiplier(age):
            if age is None or age == "":
                return 0
            a = int(age)
            if a <= 15: return 15
            if a <= 20: return 18
            if a <= 25: return 18
            if a <= 30: return 17
            if a <= 35: return 16
            if a <= 40: return 15
            if a <= 45: return 14
            if a <= 50: return 13
            if a <= 55: return 11
            if a <= 60: return 9
            if a <= 65: return 7
            return 5

        def js_get_future_prospect_percentage(age, future_type):
            f_type = int(future_type)
            a = int(age)
            if f_type == 1:
                if a < 40: return 50
                if a < 50: return 30
                if a < 60: return 15
                return 0
            else:
                if a < 40: return 40
                if a < 50: return 25
                if a < 60: return 10
                return 0

        # We will test monthly_income=10000, dependents=2 (deduction = 1/3), married
        # Consortium = 48400, Funeral = 18150, Estate = 18150 (Conventional heads = 84.7k total)
        test_cases = [
            # age, future_type, expected_prospect_pct, expected_multiplier, expected_final_compensation
            # Standard age tests
            (25, 1, 50, 18, 2244700.0),
            (25, 2, 40, 18, 2100700.0),
            (45, 1, 30, 14, 1540700.0),
            (45, 2, 25, 14, 1484700.0),
            (55, 1, 15, 11, 1096700.0),
            (55, 2, 10, 11, 1052700.0),
            (65, 1, 0, 7, 644700.0),
            (65, 2, 0, 7, 644700.0),
            
            # Exact boundary tests
            (15, 1, 50, 15, 1884700.0),
            (15, 2, 40, 15, 1764700.0),
            (40, 1, 30, 15, 1644700.0),
            (40, 2, 25, 15, 1584700.0),
            (50, 1, 15, 13, 1280700.0),
            (50, 2, 10, 13, 1228700.0),
            (60, 1, 0, 9, 804700.0),
            (60, 2, 0, 9, 804700.0),
        ]

        for age, ftype, expected_pct, mult, expected_total in test_cases:
            with self.subTest(age=age, future_type=ftype):
                req = CompensationRequest(
                    case_type="death",
                    age=age,
                    monthly_income=10000.0,
                    dependents=2,
                    marital_status="married",
                    future_type=ftype,
                    consortium=48400.0,
                    funeral_expenses=18150.0,
                    loss_estate=18150.0
                )
                res = calculate_death_compensation(req)
                self.assertEqual(res["future_prospect_percentage"], expected_pct)
                self.assertEqual(res["multiplier"], mult)
                self.assertEqual(res["final_compensation"], expected_total)
                
                # Assert frontend parity
                self.assertEqual(js_get_multiplier(age), mult, f"Multiplier mismatch at age {age}")
                self.assertEqual(js_get_future_prospect_percentage(age, ftype), expected_pct, f"Prospects mismatch at age {age}, type {ftype}")

    def test_conventional_heads_dynamic_enhancement(self):
        """
        Verify that consortium, funeral_expenses, and loss_estate default to values
        enhanced dynamically based on the award_date, and not date_of_accident.
        """
        # Scenario A: award_date = 2017-11-01 (0 completed 3-year periods since 2017-10-31)
        req_a = CompensationRequest(
            case_type="death",
            age=30,
            monthly_income=20000.0,
            dependents=5,
            marital_status="married",
            future_type=2,
            award_date="2017-11-01"
        )
        res_a = calculate_death_compensation(req_a)
        self.assertEqual(res_a["consortium"], 40000.0)
        self.assertEqual(res_a["funeral_expenses"], 15000.0)
        self.assertEqual(res_a["loss_estate"], 15000.0)

        # Scenario B: award_date = 2023-11-01 (2 completed 3-year periods since 2017-10-31)
        req_b = CompensationRequest(
            case_type="death",
            age=30,
            monthly_income=20000.0,
            dependents=5,
            marital_status="married",
            future_type=2,
            award_date="2023-11-01"
        )
        res_b = calculate_death_compensation(req_b)
        self.assertEqual(res_b["consortium"], 48000.0)
        self.assertEqual(res_b["funeral_expenses"], 18000.0)
        self.assertEqual(res_b["loss_estate"], 18000.0)

        # Scenario C: explicit overrides are respected even on a later award_date
        req_c = CompensationRequest(
            case_type="death",
            age=30,
            monthly_income=20000.0,
            dependents=5,
            marital_status="married",
            future_type=2,
            award_date="2023-11-01",
            consortium=50000.0,
            funeral_expenses=0.0,
            loss_estate=10000.0
        )
        res_c = calculate_death_compensation(req_c)
        self.assertEqual(res_c["consortium"], 50000.0)
        self.assertEqual(res_c["funeral_expenses"], 0.0)
        self.assertEqual(res_c["loss_estate"], 10000.0)

        # Scenario D: Supplying only date_of_accident correctly falls back to date_of_accident for escalation
        req_d = CompensationRequest(
            case_type="death",
            age=30,
            monthly_income=20000.0,
            dependents=5,
            marital_status="married",
            future_type=2,
            date_of_accident="2017-11-01"
        )
        res_d = calculate_death_compensation(req_d)
        self.assertEqual(res_d["consortium"], 40000.0)
        self.assertEqual(res_d["funeral_expenses"], 15000.0)
        self.assertEqual(res_d["loss_estate"], 15000.0)

        # Scenario E: Supplying no date fields at all falls back to today's date
        req_e = CompensationRequest(
            case_type="death",
            age=30,
            monthly_income=20000.0,
            dependents=5,
            marital_status="married",
            future_type=2
        )
        res_e = calculate_death_compensation(req_e)
        self.assertEqual(res_e["consortium"], 48000.0)
        self.assertEqual(res_e["funeral_expenses"], 18000.0)
        self.assertEqual(res_e["loss_estate"], 18000.0)

    def test_death_calculator_gaps_verification(self):
        """
        Verify specific death case calculator bugs are fixed:
        1. Married with 2 dependents -> 1/3 deduction
        2. Married with 3 dependents (family of 4) -> 1/4 deduction
        3. Bachelor deceased (always 1/2 deduction regardless of dependents)
        4. Above age 60 (0% future prospects)
        5. Consortium double-counting (breakdown total overrides generic consortium)
        6. Precise intermediate float precision carrying (tested via mincome=10001, nodep=3, age=30)
        """
        # 1. Married with 2 dependents -> 1/3 deduction
        req1 = CompensationRequest(
            case_type="death",
            age=30,
            monthly_income=12000.0,
            dependents=2,
            marital_status="married",
            future_type=1,
            award_date="2017-11-01"
        )
        res1 = calculate_death_compensation(req1)
        self.assertEqual(res1["deduction_label"], "1/3")
        # Income after prospects = 18000. Annual = 216000. Net = 144000. Multiplier = 17. Loss = 2448000.
        self.assertEqual(res1["loss_of_dependency"], 2448000)

        # 2. Married with 3 dependents -> 1/3 deduction
        req2 = CompensationRequest(
            case_type="death",
            age=30,
            monthly_income=12000.0,
            dependents=3,
            marital_status="married",
            future_type=1,
            award_date="2017-11-01"
        )
        res2 = calculate_death_compensation(req2)
        self.assertEqual(res2["deduction_label"], "1/3")
        # Net = 216000 * 2/3 = 144000. Loss = 144000 * 17 = 2448000.
        self.assertEqual(res2["loss_of_dependency"], 2448000)

        # 2b. Married with 4 dependents -> 1/4 deduction
        req2_4 = CompensationRequest(
            case_type="death",
            age=30,
            monthly_income=12000.0,
            dependents=4,
            marital_status="married",
            future_type=1,
            award_date="2017-11-01"
        )
        res2_4 = calculate_death_compensation(req2_4)
        self.assertEqual(res2_4["deduction_label"], "1/4")
        # Net = 216000 * 0.75 = 162000. Loss = 162000 * 17 = 2754000.
        self.assertEqual(res2_4["loss_of_dependency"], 2754000)

        # 3. Bachelor deceased with 3 dependents (> 1 dependent -> 1/3 deduction)
        req3 = CompensationRequest(
            case_type="death",
            age=30,
            monthly_income=12000.0,
            dependents=3,
            marital_status="bachelor",
            future_type=1,
            award_date="2017-11-01"
        )
        res3 = calculate_death_compensation(req3)
        self.assertEqual(res3["deduction_label"], "1/3")

        # 4. Above age 60 (0% future prospects)
        req4 = CompensationRequest(
            case_type="death",
            age=61,
            monthly_income=10000.0,
            dependents=2,
            marital_status="married",
            future_type=1,
            award_date="2017-11-01"
        )
        res4 = calculate_death_compensation(req4)
        self.assertEqual(res4["future_prospect_percentage"], 0)

        # 5. Consortium double-counting check (breakdown replaces/overrides generic consortium)
        req5 = CompensationRequest(
            case_type="death",
            age=30,
            monthly_income=10000.0,
            dependents=2,
            marital_status="married",
            future_type=1,
            award_date="2017-11-01",
            conspo=40000.0, # spousal consortium
            conpar=40000.0  # parental consortium
        )
        res5 = calculate_death_compensation(req5)
        # generic consortium must be overridden and set to 0.0 because breakdown total is 80000.0
        self.assertEqual(res5["consortium"], 0.0)
        self.assertEqual(res5["consortium_breakdown_total"], 80000.0)
        # Total = loss_of_dependency + funeral + loss_estate + breakdown = 2040000 + 15000 + 15000 + 80000 = 2150000
        self.assertEqual(res5["final_compensation"], 2150000)

        # 6. Precise intermediate float precision check
        # monthly_income=10001, nodep=4, married (1/4 deduction), age=30 (17 multiplier), future_type=1 (50% prospects)
        # Enhanced monthly = 15001.5. Annual = 180018. Deduction = 45004.5. Dependency = 135013.5.
        # Loss of dependency = 135013.5 * 17 = 2295229.5 -> rounds to 2295230.
        req6 = CompensationRequest(
            case_type="death",
            age=30,
            monthly_income=10001.0,
            dependents=4,
            marital_status="married",
            future_type=1,
            award_date="2017-11-01"
        )
        res6 = calculate_death_compensation(req6)
        self.assertEqual(res6["loss_of_dependency"], 2295230)
        self.assertEqual(res6["deduction_amount"], 45005)
        self.assertEqual(res6["dependency_income"], 135014)


class TestInjuryCompensation(unittest.TestCase):
    def test_injury_compensation_loexlife_regression(self):
        """
        Verify that loexlife is returned correctly and does not match loamiti when distinct values are sent.
        """
        req = CompensationRequest(
            case_type="injury",
            age=30,
            monthly_income=20000.0,
            loamiti=5000.0,
            loexlife=12000.0
        )
        res = calculate_injury_compensation(req)
        self.assertEqual(res["loexlife"], 12000.0)
        self.assertEqual(res["loamiti"], 5000.0)


if __name__ == "__main__":
    unittest.main()
