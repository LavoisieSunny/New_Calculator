import unittest
from unittest.mock import patch, MagicMock
from backend.parser_heuristics import parse_hindi_extracted_text

class TestHindiParser(unittest.TestCase):
    def test_hindi_parser_single_line_heuristics(self):
        text_lines = [
            "नाम और पिता का नाम : राजेश कुमार पुत्र श्री रमेश कुमार",
            "आयु लगभग 35 वर्ष",
            "मासिक आय 12,500 रूपये",
            "दिनांक 12.05.2025 को दुर्घटना हुई",
            "वाहन क्रमांक MP07CA1234",
            "पालिसी नंबर POL-987654-XYZ",
            "न्यू इंडिया इन्शोरेंस कंपनी",
            "प्रतिकर राशि रूपये 1,50,000",
            "चिकित्सा व्यय रू 15,000/-",
            "शारीरिक एवं मानसिक वेदना 10,000",
            "परिवहन व्यय 5,000",
            "विशेष खुराक व्यय 3,000",
            "परिचारक व्यय 2,000",
            "भविष्य चिकित्सा व्यय 25,000",
            "आय की हानि 12,500",
            "स्थायी अपंगता 40 प्रतिशत"
        ]
        
        # Test basic regex extraction
        res = parse_hindi_extracted_text(text_lines)
        
        self.assertEqual(res.get("injured_name"), "राजेश")
        self.assertEqual(res.get("father_name"), "रमेश")
        self.assertEqual(res.get("age"), 35)
        self.assertEqual(res.get("monthly_income"), 12500.0)
        self.assertEqual(res.get("date_of_accident"), "12.05.2025")
        self.assertEqual(res.get("vehicle_number"), "MP07CA1234")
        self.assertEqual(res.get("policy_number"), "POL-987654-XYZ")
        self.assertEqual(res.get("insurance_company"), "न्यू इंडिया इन्शोरेंस कंपनी")
        self.assertEqual(res.get("award_amount"), 150000.0)
        
        self.assertEqual(res.get("medical_expenses"), 15000.0)
        self.assertEqual(res.get("pain_and_suffering"), 10000.0)
        self.assertEqual(res.get("transportation"), 5000.0)
        self.assertEqual(res.get("special_diet"), 3000.0)
        self.assertEqual(res.get("attender_charges"), 2000.0)
        self.assertEqual(res.get("future_medical_expenses"), 25000.0)
        self.assertEqual(res.get("loss_of_income"), 12500.0)
        self.assertEqual(res.get("disability"), 40)
        
        self.assertEqual(res.get("case_type"), "injury")

    def test_hindi_parser_consecutive_line_lookahead(self):
        # Test table layouts where keywords and values are split across lines
        text_lines = [
            "चिकित्सा व्यय",
            "| 15,000 |",
            "शारीरिक एवं मानसिक वेदना",
            "रू 10,000/-",
            "परिवहन व्यय",
            "| 5,000 |",
            "विशेष खुराक व्यय",
            "3,000",
            "परिचारक व्यय",
            "| 2,000",
            "भविष्य चिकित्सा व्यय",
            "25,000",
            "आय की हानि",
            "12,500",
            "स्थायी अपंगता",
            "40 %",
            "मासिक आय",
            "| 12,500 |"
        ]
        
        res = parse_hindi_extracted_text(text_lines)
        
        self.assertEqual(res.get("medical_expenses"), 15000.0)
        self.assertEqual(res.get("pain_and_suffering"), 10000.0)
        self.assertEqual(res.get("transportation"), 5000.0)
        self.assertEqual(res.get("special_diet"), 3000.0)
        self.assertEqual(res.get("attender_charges"), 2000.0)
        self.assertEqual(res.get("future_medical_expenses"), 25000.0)
        self.assertEqual(res.get("loss_of_income"), 12500.0)
        self.assertEqual(res.get("disability"), 40)
        self.assertEqual(res.get("monthly_income"), 12500.0)

    @patch("backend.llm_client.ai_data_recovery")
    def test_hindi_parser_ai_fallback(self, mock_recovery):
        # Mock LLM response for missing fields
        mock_recovery.return_value = {
            "disability_percentage": 35.0,
            "medical_expenses": 12000.0,
            "monthly_income": 10000.0,
            "award_amount": 90000.0
        }
        
        # Sparse text that triggers AI recovery fallback due to missing fields
        text_lines = [
            "चोट की श्रेणी"
        ]
        
        res = parse_hindi_extracted_text(text_lines)
        
        self.assertTrue(res.get("ai_recovery_triggered"))
        self.assertEqual(res.get("disability"), 35.0)
        self.assertEqual(res.get("medical_expenses"), 12000.0)
        self.assertEqual(res.get("monthly_income"), 10000.0)
        self.assertEqual(res.get("award_amount"), 90000.0)

if __name__ == "__main__":
    unittest.main()
