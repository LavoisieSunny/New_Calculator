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

    def test_clean_person_name_utility(self):
        from backend.parser_heuristics import clean_person_name
        # Test honorific stripping
        self.assertEqual(clean_person_name("Shri, Jaychand Chugwani"), "Jaychand Chugwani")
        self.assertEqual(clean_person_name("Late Shri Jaychand"), "Jaychand")
        self.assertEqual(clean_person_name("Smt. Jane Doe"), "Jane Doe")
        self.assertEqual(clean_person_name("Km. Kumari Sneha"), "Sneha")
        self.assertEqual(clean_person_name("Late Robert"), "Robert")
        
        # Test relationship fragment stripping
        self.assertEqual(clean_person_name("Kamal Kumar S/o Shri, Jaychand C..."), "Kamal Kumar")
        self.assertEqual(clean_person_name("Jane Doe W/o John Doe"), "Jane Doe")
        self.assertEqual(clean_person_name("Baby D/o Mary"), "Baby")
        self.assertEqual(clean_person_name("John C/o Uncle"), "John")
        self.assertEqual(clean_person_name("Kamal Kumar s/o Jaychand"), "Kamal Kumar")
        
        # Test strip of trailing/leading commas/dots/spaces
        self.assertEqual(clean_person_name(" ,. Shri, Jaychand. ,"), "Jaychand")

    @patch('backend.llm_client.generate_response')
    @patch('backend.llm_client.classify_case_type_by_ocr_text')
    def test_ai_data_recovery_name_cleaning(self, mock_classify, mock_generate):
        mock_classify.return_value = "injury"
        mock_generate.return_value = """{
            "case_type": {"value": "injury", "confidence": 0.95},
            "claimant_name": {"value": "Kamal Kumar S/o Shri, Jaychand C...", "confidence": 0.98},
            "father_name": {"value": "Shri, Jaychand Chugwani", "confidence": 0.9}
        }"""

        res = ai_data_recovery("some random ocr text")
        self.assertEqual(res["claimant_name"], "Kamal Kumar")
        self.assertEqual(res["father_name"], "Jaychand Chugwani")

    def test_extract_age_from_text_utility(self):
        from backend.parser_heuristics import extract_age_from_text
        text = "Kamal Kumar is claimant. Kamal Kumar was aged about 22 years at the time. His father is Shri Jaychand who is 53 years old."
        
        # Test proximity search targeting claimant (Kamal Kumar)
        age, ctx = extract_age_from_text(text, claimant_name="Kamal Kumar", case_type="injury")
        self.assertEqual(age, 22)
        
        # Test proximity search targeting father/other person
        age, ctx = extract_age_from_text(text, claimant_name="Jaychand", case_type="injury")
        self.assertEqual(age, 53)
        
        # Test global fallback search when target name has no close age match
        age, ctx = extract_age_from_text("Deceased person was aged about 45 years. Another line.", claimant_name="John Doe", case_type="death")
        self.assertEqual(age, 45)

    @patch('backend.llm_client.generate_response')
    @patch('backend.llm_client.classify_case_type_by_ocr_text')
    def test_ai_data_recovery_age_override(self, mock_classify, mock_generate):
        mock_classify.return_value = "injury"
        
        # LLM returns age as null
        mock_generate.return_value = """{
            "case_type": {"value": "injury", "confidence": 0.95},
            "claimant_name": {"value": "Kamal Kumar", "confidence": 0.98},
            "age": {"value": null, "confidence": 0.0}
        }"""
        
        # Proximity matches 22
        res = ai_data_recovery("Kamal Kumar is claimant. Kamal Kumar is aged about 22 years.")
        self.assertEqual(res["age"], 22)
        self.assertEqual(res["confidence_scores"]["age"]["confidence"], 0.85)

    @patch('backend.llm_client.generate_response')
    @patch('backend.llm_client.classify_case_type_by_ocr_text')
    def test_ai_data_recovery_relationship_and_marital_status_guard(self, mock_classify, mock_generate):
        mock_classify.return_value = "death"
        # Mock LLM returning Wife of deceased and married, which is incorrect
        mock_generate.return_value = """{
            "case_type": {"value": "death", "confidence": 0.95},
            "claimant_name": {"value": "Parvati Singh", "confidence": 0.98},
            "deceased_name": {"value": "Anjani Singh", "confidence": 0.99},
            "claimant_relationship_type": {"value": "Wife of deceased", "confidence": 0.9},
            "claimant_relationship_to_deceased": {"value": "Wife of deceased", "confidence": 0.9},
            "marital_status": {"value": "married", "confidence": 0.9},
            "age": {"value": 22, "confidence": 0.9}
        }"""
        
        # In this OCR text, Parvati Singh is W/o Vishnudev Singh (not Anjani Singh)
        ocr_text = "Parvati Singh W/o Vishnudev Singh\nDeceased was Anjani Singh aged about 22 years.\nclaimant is the mother of the deceased."
        
        res = ai_data_recovery(ocr_text)
        
        # Relationship and marital status should be overridden by the guard
        self.assertEqual(res.get("claimant_relationship_type"), "Mother")
        self.assertEqual(res.get("marital_status"), "single")

    @patch('backend.llm_client.generate_response')
    @patch('backend.llm_client.classify_case_type_by_ocr_text')
    def test_ai_data_recovery_relationship_unconfirmed_guard(self, mock_classify, mock_generate):
        mock_classify.return_value = "death"
        mock_generate.return_value = """{
            "case_type": {"value": "death", "confidence": 0.95},
            "claimant_name": {"value": "Parvati Singh", "confidence": 0.98},
            "deceased_name": {"value": "Anjani Singh", "confidence": 0.99},
            "claimant_relationship_type": {"value": "Wife of deceased", "confidence": 0.9},
            "claimant_relationship_to_deceased": {"value": "Wife of deceased", "confidence": 0.9},
            "marital_status": {"value": "married", "confidence": 0.9},
            "age": {"value": 22, "confidence": 0.9}
        }"""
        
        # Text has W/o but husband doesn't match and there is no mother/father keywords in text
        ocr_text = "Parvati Singh W/o Vishnudev Singh\nDeceased was Anjani Singh aged about 22 years."
        
        res = ai_data_recovery(ocr_text)
        
        # Guard overrides relationship to empty and marital status to single
        self.assertEqual(res.get("claimant_relationship_type"), "")
        self.assertEqual(res.get("marital_status"), "single")

if __name__ == "__main__":
    unittest.main()
