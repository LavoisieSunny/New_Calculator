import sys
from unittest.mock import MagicMock

# ── Mock backend.ocr Module before any other imports ──────────────────────────
# This avoids importing paddleocr -> sentence_transformers -> pyarrow,
# preventing the Windows fatal access violation crash under Python 3.13.
mock_ocr = MagicMock()
mock_ocr.call_paddle_ocr.side_effect = lambda image_path, page_num=1: mock_call_paddle_ocr(image_path, page_num)
mock_ocr.guard_and_downscale_image = lambda img: img
mock_ocr.classify_scanned_page.return_value = "content"
mock_ocr.is_vision_model_available.return_value = False
sys.modules['backend.ocr'] = mock_ocr

# Global test context to tell mock OCR what text to return for each file
current_pdf_context = None

def mock_call_paddle_ocr(image_path, page_num=1):
    global current_pdf_context
    if current_pdf_context and "MA_20_2026" in current_pdf_context:
        if page_num == 1:
            return (["IN THE HIGH COURT OF MADHYA PRADESH", "MISCELLANEOUS APPEAL NO. 20 OF 2026", "MEMO OF APPEAL"], [0.99], 0.0)
        elif page_num == 2:
            return (["GROUNDS OF APPEAL", "1. The learned Tribunal erred in assessing compensation"], [0.99], 0.0)
        elif page_num == 3:
            return (["PRAYER", "It is therefore prayed that this Hon'ble Court may be pleased to enhance"], [0.99], 0.0)
    elif current_pdf_context and "MA_10076_2025" in current_pdf_context:
        if page_num == 1:
            return (["IN THE HIGH COURT OF MADHYA PRADESH", "MISCELLANEOUS APPEAL NO. 10076 OF 2025", "MEMO OF APPEAL"], [0.99], 0.0)
        elif page_num == 2:
            return (["GROUNDS OF APPEAL", "1. The award of the Tribunal is too low"], [0.99], 0.0)
        elif page_num == 3:
            return (["PRAYER", "It is prayed to enhance the compensation amount"], [0.99], 0.0)
        elif page_num >= 4:
            return (["न्यायालय मोटर दुर्घटना दावा अधिकरण", "निर्णय", "आवेदक का जन्म दिनांक 30.10.1969 उल्लेखित है"], [0.99], 0.0)
    return ([], [0.0], 0.0)


import unittest
import os
from backend.track_detection import detect_case_track
from backend.parser_heuristics import parse_extracted_text, parse_hindi_extracted_text

class TestParserFixesAndTrackRouting(unittest.TestCase):
    def test_detect_case_track_routing(self):
        """
        Verify that detect_case_track correctly routes MA_20_2026.pdf and
        MA_10076_2025.pdf to 'high_court'.
        """
        global current_pdf_context
        pdf_path_1 = r"C:\Users\lavoi\Desktop\Miracle\pdfs\compensation\MA_20_2026.pdf"
        pdf_path_2 = r"C:\Users\lavoi\Desktop\Miracle\pdfs\compensation\MA_10076_2025_d.pdf"
        
        # Verify files exist
        self.assertTrue(os.path.exists(pdf_path_1), f"File not found: {pdf_path_1}")
        self.assertTrue(os.path.exists(pdf_path_2), f"File not found: {pdf_path_2}")
        
        current_pdf_context = "MA_20_2026"
        res1 = detect_case_track(pdf_path_1)
        
        current_pdf_context = "MA_10076_2025"
        res2 = detect_case_track(pdf_path_2)
        
        self.assertEqual(res1["track"], "high_court")
        self.assertEqual(res2["track"], "high_court")

    def test_parse_extracted_text_dob_autofill_guard(self):
        """
        Verify that parse_extracted_text does NOT synthesize/guess a DOB
        when the source text only states an age and does not contain a birth date.
        """
        text_lines = [
            "Claimant: Smt. Geeta Devi",
            "Age of the claimant is 45 years at the time of accident",
            "Date of Accident: 10-12-2023",
            "Tribunal awarded total compensation: 3,00,000/-"
        ]
        suggestions = parse_extracted_text(text_lines, case_type="injury")
        
        # Verify DOB-autofill guard: no DOB should be guessed/calculated from age
        self.assertEqual(suggestions.get("date_of_birth"), "")

    def test_parse_extracted_text_deceased_age_death_case(self):
        """
        Verify that parse_extracted_text extracts the deceased's age (45)
        rather than the claimant/petitioner's age (30) in a death case.
        """
        text_lines = [
            "--- CLAIMANT SECTION ---",
            "1. Smt. Rani Devi, wife of late Shri Ramesh, aged 30 years.",
            "2. Master Rohit, son of late Shri Ramesh, aged 5 years.",
            "--- CAUSE TITLE / PETITION ---",
            "This petition is filed on the death of Shri Ramesh in a motor accident.",
            "The deceased Ramesh was aged 45 years at the time of accident.",
            "--- AWARD SECTION ---",
            "Total Compensation awarded: 12,0,000/-"
        ]
        
        # Run parsing under case_type='death'
        suggestions = parse_extracted_text(text_lines, case_type="death")
        
        # Should extract the deceased's age (45), not the claimant's age (30)
        self.assertEqual(suggestions.get("age"), 45)

    def test_parse_hindi_extracted_text_unchanged(self):
        """
        Verify that parse_hindi_extracted_text output is byte-for-byte unchanged
        on a sample lower-court Hindi award.
        """
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
        
        res = parse_hindi_extracted_text(text_lines)
        
        # Expected values from original test_hindi_parser.py
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
