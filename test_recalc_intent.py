import unittest
import sys
import os
import asyncio
from unittest.mock import patch

# Append project root directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.recalc_intent import parse_recalc_intent, run_recalculation
from backend.main import chat_with_pdf, PDFChatRequest

class TestRecalcIntent(unittest.TestCase):
    def test_parse_recalc_intent_informational(self):
        # Plain factual questions should not trigger recalculation
        self.assertIsNone(parse_recalc_intent("What is the disability percentage in this case?", "injury"))
        self.assertIsNone(parse_recalc_intent("how many dependents did the deceased have?", "death"))
        self.assertIsNone(parse_recalc_intent("tell me about the medical expenses", "injury"))

    def test_parse_recalc_intent_valid_recalc(self):
        # What-if prompts should trigger recalculation
        res1 = parse_recalc_intent("what if disability is 40%", "injury")
        self.assertIsNotNone(res1)
        self.assertEqual(res1[0], "disability")
        self.assertEqual(res1[1], 40.0)

        res2 = parse_recalc_intent("recalculate with medical expenses 80000", "injury")
        self.assertIsNotNone(res2)
        self.assertEqual(res2[0], "medical_expenses")
        self.assertEqual(res2[1], 80000.0)

        res3 = parse_recalc_intent("what if age is 35", "death")
        self.assertIsNotNone(res3)
        self.assertEqual(res3[0], "age")
        self.assertEqual(res3[1], 35.0)

        # Refinement & tolerance test cases
        res4 = parse_recalc_intent("attendant charges is 10000", "injury")
        self.assertIsNotNone(res4)
        self.assertEqual(res4, ("attender_charges", 10000.0, "attendant charges"))

        # Regex tolerance test (contains extra word "are" or similar between synonym and cue)
        res5 = parse_recalc_intent("attendant charges are 12000", "injury")
        self.assertIsNotNone(res5)
        self.assertEqual(res5, ("attender_charges", 12000.0, "attendant charges"))

    def test_run_recalculation_injury(self):
        parsed_fields = {
            "case_type": "injury",
            "age": 30,
            "monthly_income": 15000,
            "disability": 10,
            "award_amount": 100000,
        }
        calculator_result = {
            "case_type": "injury",
            "final_amount": 120000,
        }

        # What if monthly income is 20000
        res = run_recalculation("what if monthly income is 20000", parsed_fields, calculator_result)
        self.assertIsNotNone(res)
        self.assertIn("What-if recalculation", res["response"])
        self.assertIn("Revised Total: Rs.", res["response"])
        self.assertEqual(res["recalculation"]["changed_field"], "monthly_income")
        self.assertEqual(res["recalculation"]["changed_value"], 20000.0)

    def test_chatbot_endpoint_recalc_bypass(self):
        mock_payload = {
            "question": "what if disability is 50%",
            "parsed_fields": {
                "case_type": "injury",
                "age": 25,
                "monthly_income": 10000,
                "disability": 20,
                "award_amount": 50000
            },
            "calculator_result": {
                "case_type": "injury",
                "final_amount": 150000
            }
        }
        
        request = PDFChatRequest(**mock_payload)
        
        # Run async function using asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # We don't mock LLM because it should bypass the LLM and return recalculation directly
            result = loop.run_until_complete(chat_with_pdf(request))
        finally:
            loop.close()
            
        self.assertIsNotNone(result)
        self.assertIn("recalculation", result)
        self.assertIn("What-if recalculation", result["response"])
        self.assertEqual(result["recalculation"]["changed_field"], "disability")
        self.assertEqual(result["recalculation"]["changed_value"], 50.0)

if __name__ == "__main__":
    unittest.main()
