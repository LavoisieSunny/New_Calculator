import unittest
from unittest.mock import patch, MagicMock
from backend.llm_client import ai_data_recovery

class TestLLMClient(unittest.TestCase):

    @patch('backend.llm_client.generate_response')
    @patch('backend.llm_client.classify_case_type_by_ocr_text')
    def test_ai_data_recovery_aliases_and_no_overwrite(self, mock_classify, mock_generate):
        mock_classify.return_value = "death"
        # Mocking LLM returning a valid JSON with distinct deceased_name and claimant_name
        mock_generate.return_value = """{
            "case_type": {"value": "death", "confidence": 0.95},
            "claimant_name": {"value": "Jane Doe", "confidence": 0.98},
            "deceased_name": {"value": "John Doe", "confidence": 0.99},
            "father_name": {"value": "Robert Doe", "confidence": 0.9}
        }"""

        res = ai_data_recovery("some random ocr text")
        
        # Verify deceased_name is NOT overwritten by claimant_name ("Jane Doe")
        self.assertEqual(res["deceased_name"], "John Doe")
        self.assertEqual(res["claimant_name"], "Jane Doe")
        self.assertEqual(res["name"], "John Doe") # Deceased name aliased to name in death case
        self.assertEqual(res["father_name"], "Robert Doe")

    @patch('backend.llm_client.generate_response')
    @patch('backend.llm_client.classify_case_type_by_ocr_text')
    def test_ai_data_recovery_injury_aliases(self, mock_classify, mock_generate):
        mock_classify.return_value = "injury"
        mock_generate.return_value = """{
            "case_type": {"value": "injury", "confidence": 0.95},
            "claimant_name": {"value": "Jane Doe", "confidence": 0.98}
        }"""

        res = ai_data_recovery("some random ocr text")
        self.assertEqual(res["claimant_name"], "Jane Doe")
        self.assertEqual(res["name"], "Jane Doe") # Claimant name aliased to name in injury case

    @patch('backend.llm_client.generate_response')
    def test_ai_data_recovery_graceful_error_handling(self, mock_generate):
        # Mocking LLM returning invalid/garbage JSON
        mock_generate.return_value = "This is not a valid JSON structure."

        # Should not raise an exception, but return the fallback dict
        res = ai_data_recovery("some random ocr text")
        self.assertIn("ai_recovery_error", res)
        self.assertEqual(res["ai_recovery_error"], "AI-assisted recovery unavailable for this document — please fill remaining fields manually.")
        self.assertEqual(res["raw_response_preview"], "This is not a valid JSON structure.")

    @patch('backend.llm_client.generate_response')
    def test_ai_data_recovery_prose_wrapped_json_repair(self, mock_generate):
        # Mocking LLM returning a prose-wrapped JSON structure
        mock_generate.return_value = """Here is the extracted information in JSON format:
        {
            "case_type": {"value": "injury", "confidence": 0.95},
            "claimant_name": {"value": "Jane Doe", "confidence": 0.98}
        }
        I hope this helps!"""

        res = ai_data_recovery("some random ocr text")
        # Ensure it successfully repaired and parsed
        self.assertNotIn("ai_recovery_error", res)
        self.assertEqual(res["claimant_name"], "Jane Doe")
        self.assertEqual(res["case_type"], "injury")

    @patch('backend.llm_client.generate_response')
    def test_ai_data_recovery_invalid_shape_rejection(self, mock_generate):
        # Mocking LLM returning valid JSON syntax but invalid/unrelated keys (bad shape)
        mock_generate.return_value = """{
            "some_irrelevant_key": "some_value",
            "another_key": "value"
        }"""

        res = ai_data_recovery("some random ocr text")
        # Ensure shape validation rejects this and returns recovery error
        self.assertIn("ai_recovery_error", res)
        self.assertEqual(res["ai_recovery_error"], "AI-assisted recovery unavailable for this document — please fill remaining fields manually.")

    @patch('backend.llm_client.generate_response')
    @patch('backend.llm_client.classify_case_type_by_ocr_text')
    def test_ai_data_recovery_sanitizer(self, mock_classify, mock_generate):
        mock_classify.return_value = "injury"
        # Mocking LLM returning some blocklisted string answers for various fields
        mock_generate.return_value = """{
            "case_type": {"value": "injury", "confidence": 0.95},
            "claimant_name": {"value": "Jane Doe", "confidence": 0.98},
            "father_name": {"value": "not explicitly stated", "confidence": 0.9},
            "accident_place": {"value": "Not Stated", "confidence": 0.8},
            "judge_name": {"value": "unclear", "confidence": 0.7},
            "vehicle_number": {"value": "N/A", "confidence": 0.6},
            "insurance_company": {"value": "unknown", "confidence": 0.55},
            "fir_number": {"value": "not mentioned in document", "confidence": 0.5},
            "case_number": {"value": "not found in text", "confidence": 0.4}
        }"""

        res = ai_data_recovery("some random ocr text")
        
        # Valid name is preserved
        self.assertEqual(res["claimant_name"], "Jane Doe")
        
        # Blocklisted non-answer values are mapped to None
        self.assertIsNone(res.get("father_name"))
        self.assertIsNone(res.get("place_of_accident")) # accident_place maps to place_of_accident
        self.assertIsNone(res.get("judge_name"))
        self.assertIsNone(res.get("vehicle_number"))
        self.assertIsNone(res.get("insurance_company"))
        self.assertIsNone(res.get("fir_number"))
        self.assertIsNone(res.get("case_number"))

        # Verify that their confidence score was set to 0.0
        scores = res.get("confidence_scores", {})
        self.assertEqual(scores.get("father_name", {}).get("confidence"), 0.0)
        self.assertEqual(scores.get("accident_place", {}).get("confidence"), 0.0)
        self.assertEqual(scores.get("judge_name", {}).get("confidence"), 0.0)
        self.assertEqual(scores.get("vehicle_number", {}).get("confidence"), 0.0)
        self.assertEqual(scores.get("insurance_company", {}).get("confidence"), 0.0)
        self.assertEqual(scores.get("fir_number", {}).get("confidence"), 0.0)
        self.assertEqual(scores.get("case_number", {}).get("confidence"), 0.0)

if __name__ == "__main__":
    unittest.main()
