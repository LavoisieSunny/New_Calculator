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

    def test_numbered_list_format(self):
        # Verify that leading list numbers are stripped and not mistaken for the amount
        text_lines = [
            "1. चिकित्सा व्यय रू 15,000",
            "२) विशेष खुराक व्यय 3,000",
            "[3] परिचारक व्यय 2,000",
            "(४) परिवहन व्यय 5,000"
        ]
        res = parse_hindi_extracted_text(text_lines)
        self.assertEqual(res.get("medical_expenses"), 15000.0)
        self.assertEqual(res.get("special_diet"), 3000.0)
        self.assertEqual(res.get("attender_charges"), 2000.0)
        self.assertEqual(res.get("transportation"), 5000.0)

    def test_new_fields_and_phrasings(self):
        # Phrasing set 1: Loss of future prospects
        phrasings_prospects = [
            "आवेदक के भविष्य में प्रगति करने एवं ओर अधिक आय प्राप्त करने से वंचित होने के लिए 10,00,000",
            "भविष्य की प्रगति तथा उन्नति की हानि हेतु प्रतिकर राशि 5,50,000",
            "भविष्य में आय की संभावनाओं और विकास से वंचित होने के निमित्त 2,00,000/-"
        ]
        for line in phrasings_prospects:
            res = parse_hindi_extracted_text([line])
            self.assertIn(res.get("loss_of_future_prospects"), [1000000.0, 550000.0, 200000.0])

        # Phrasing set 2: Loss of amenities
        phrasings_amenities = [
            "आवेदक द्वारा भविष्य में आनंदपूर्ण जीवन जीने से वंचित होने के लिए 2,50,000",
            "जीवन के सुखों तथा आनंद से वंचित रहने की क्षतिपूर्ति 1,80,000/-",
            "सुखमय जीवन जीने के अधिकार से वंचित होने पर 3,00,000",
            "जीवन के सुखों की हानि (loss of amenities) हेतु 1,20,000"
        ]
        for line in phrasings_amenities:
            res = parse_hindi_extracted_text([line])
            self.assertIn(res.get("loss_of_amenities"), [250000.0, 180000.0, 300000.0, 120000.0])

    def test_combined_clause_deduplication(self):
        # A combined line that matches diet, doctor fees (medical), transport, future medical
        text_lines = [
            "विशेष आहार एवं डॉ. की फीस परिवहन एवं भविष्य में उपचार होने वाले व्यय - 1,00,000/-"
        ]
        res = parse_hindi_extracted_text(text_lines)
        
        # Verify Rule 4 bundling logic (target special_diet gets the full amount, transport gets 0, bundled_source=True)
        self.assertEqual(res.get("special_diet"), 100000.0)
        self.assertEqual(res.get("transportation"), 0.0)
        self.assertTrue(res.get("bundled_source"))

    def test_merge_rules_pain_and_loss(self):
        text_lines = [
            "1. स्थायी अपंगता हेतु क्षतिपूर्ति 1,50,000",
            "2. शारीरिक एवं मानसिक वेदना 10,000",
            "3. आवेदक के भविष्य में प्रगति करने एवं ओर अधिक आय प्राप्त करने से वंचित होने के लिए 2,00,000",
            "4. आवेदक द्वारा भविष्य में आनंदपूर्ण जीवन जीने से वंचित होने के लिए 2,50,000",
            "5. सहायता व्यय 5,000",
            "6. स्थायी निर्योग्यता 39 प्रतिशत पायी गई थी"
        ]
        res = parse_hindi_extracted_text(text_lines)
        self.assertEqual(res.get("pain_and_suffering"), 160000.0) # 150000 + 10000
        self.assertEqual(res.get("loss_of_income"), 450000.0) # 200000 + 250000
        self.assertEqual(res.get("attender_charges"), 5000.0)
        self.assertEqual(res.get("disability"), 39.0)

    def test_ambiguous_line_manual_review(self):
        text_lines = [
            "चिकित्सा एवं सहायता व्यय 50,000"
        ]
        res = parse_hindi_extracted_text(text_lines)
        self.assertEqual(res.get("medical_expenses"), 0.0)
        self.assertEqual(res.get("attender_charges"), 0.0)
        self.assertIn("needs_manual_review", res)
        self.assertIn("चिकित्सा एवं सहायता व्यय 50,000", res["needs_manual_review"])

    def test_safety_net_mismatch(self):
        # Test Case 1: Matching sum
        text_lines_match = [
            "चिकित्सा व्यय 50,000",
            "शारीरिक एवं मानसिक वेदना 10,000",
            "कुल प्रतिकर राशि 60,000"
        ]
        res_match = parse_hindi_extracted_text(text_lines_match)
        self.assertFalse(res_match.get("mismatch_warning", False))

        # Test Case 2: Mismatching sum
        text_lines_mismatch = [
            "चिकित्सा व्यय 50,000",
            "शारीरिक एवं मानसिक वेदना 10,000",
            "कुल प्रतिकर राशि 1,00,000"
        ]
        res_mismatch = parse_hindi_extracted_text(text_lines_mismatch)
        self.assertTrue(res_mismatch.get("mismatch_warning"))
        self.assertIn("mismatch_details", res_mismatch)
        self.assertIn("60,000", res_mismatch.get("mismatch_details"))
        self.assertIn("100,000", res_mismatch.get("mismatch_details"))

if __name__ == "__main__":
    unittest.main()
