import unittest

def apply_autofill_with_protection(user_case_type, llm_case_type):
    """
    Simulates the workstation case type overwrite protection logic.
    If the user has manually selected a case type, it cannot be overwritten by LLM suggestions.
    """
    overwrite_blocked = False
    final_case_type = user_case_type
    
    if user_case_type and user_case_type != "":
        if llm_case_type and llm_case_type != user_case_type:
            overwrite_blocked = True
        final_case_type = user_case_type
    else:
        final_case_type = llm_case_type or "death"
        
    return final_case_type, overwrite_blocked

class TestCaseTypeProtection(unittest.TestCase):
    def test_overwrite_protection_injury_selected(self):
        # Scenario: User manually selects: case_type = "injury"
        user_case_type = "injury"
        llm_suggestions = {
            "case_type": "death",
            "name": "Sneha"
        }
        
        final_case_type, overwrite_blocked = apply_autofill_with_protection(
            user_case_type, llm_suggestions.get("case_type")
        )
        
        # Assertions
        self.assertEqual(final_case_type, "injury", "User selection must be preserved")
        self.assertTrue(overwrite_blocked, "LLM overwrite must be blocked")
        self.assertNotEqual(final_case_type, "death", "Injury workflow remains active")

    def test_overwrite_protection_death_selected(self):
        # Scenario: User manually selects: case_type = "death"
        user_case_type = "death"
        llm_suggestions = {
            "case_type": "injury",
            "name": "Amit"
        }
        
        final_case_type, overwrite_blocked = apply_autofill_with_protection(
            user_case_type, llm_suggestions.get("case_type")
        )
        
        # Assertions
        self.assertEqual(final_case_type, "death", "User selection must be preserved")
        self.assertTrue(overwrite_blocked, "LLM overwrite must be blocked")
        self.assertNotEqual(final_case_type, "injury", "Death workflow remains active")

    def test_no_protection_when_user_selection_empty(self):
        # Scenario: User has not selected a case type yet
        user_case_type = ""
        llm_suggestions = {
            "case_type": "injury",
            "name": "Sneha"
        }
        
        final_case_type, overwrite_blocked = apply_autofill_with_protection(
            user_case_type, llm_suggestions.get("case_type")
        )
        
        # Assertions
        self.assertEqual(final_case_type, "injury", "LLM suggestion should apply when empty")
        self.assertFalse(overwrite_blocked, "Overwrite is not blocked since user selection was empty")

    def test_hindi_case_type_detection(self):
        from backend.llm_client import classify_case_type_by_ocr_text
        
        # 1. Simulated Bhopal Injury Award containing Hindi injury keywords (e.g. स्थायी अपंगता, चोट)
        bhopal_injury_text = (
            "अधिकरण भोपाल (म.प्र.)\n"
            "मोटर दुर्घटना दावा क्रमांक 123/2024\n"
            "आवेदक को दुर्घटना में स्थायी अपंगता (Permanent Disability) कारित हुई है।\n"
            "चिकित्सा बोर्ड ने आवेदक की स्थायी निःशक्तता 40 प्रतिशत निर्धारित की है।\n"
            "आवेदक को शारीरिक एवं मानसिक वेदना के लिए प्रतिकर दिया जाता है।"
        )
        
        # 2. Simulated Rewa Death Award containing Hindi death keywords (e.g. मृत्यु, मृतक, स्वर्गीय)
        rewa_death_text = (
            "दावा अधिकरण रीवा (म.प्र.)\n"
            "दुर्घटना में मृतक सुरेश का देहांत हो गया।\n"
            "मृतक की मृत्यु के कारण उसके वैध वारिस (विधवा एवं बच्चे) आश्रित हैं।\n"
            "अत: मृतक की मृत्यु के संबंध में प्रतिकर का निर्धारण निम्नानुसार किया जाता है:\n"
            "स्वर्गीय सुरेश की आयु दुर्घटना के समय 35 वर्ष थी।"
        )
        
        self.assertEqual(classify_case_type_by_ocr_text(bhopal_injury_text), "injury")
        self.assertEqual(classify_case_type_by_ocr_text(rewa_death_text), "death")

    def test_mixed_signal_injury_case_gating(self):
        from backend.parser_heuristics import parse_extracted_text
        
        # Scenario: A survivor's disability claim, but text mentions co-passenger's death in passing
        mixed_signal_text = (
            "--- PAGE 1 ---\n"
            "CLAIM PETITION BEFORE THE TRIBUNAL\n"
            "This is a claim by the injured survivor Amit Kumar who suffered 40% permanent disability.\n"
            "The claimant paid Rs. 15,000 for medical expenses.\n"
            "Incidental note: Co-passenger Rajesh died in the same fatal collision and his legal heirs filed a separate death claim."
        )
        
        lines = mixed_signal_text.split("\n")
        
        # When case_type="injury" is explicitly passed, the parser should clear all death-specific fields
        # (even though 'died', 'fatal', and 'death' keywords exist in the raw text).
        suggestions = parse_extracted_text(lines, case_type="injury")
        
        # Death fields must be completely empty/unset
        self.assertEqual(suggestions.get("case_type"), "injury")
        self.assertEqual(suggestions.get("deceased_name"), "")
        self.assertEqual(suggestions.get("dependents"), "")
        self.assertEqual(suggestions.get("consortium"), 0.0)
        self.assertEqual(suggestions.get("funeral_expenses"), 0.0)
        self.assertEqual(suggestions.get("loss_estate"), 0.0)
        
        # Injury fields must be successfully parsed/preserved
        self.assertEqual(suggestions.get("disability"), 40.0)
        self.assertEqual(suggestions.get("medical_expenses"), 15000.0)

    def test_hindi_appeal_memo_enhancement_verdict(self):
        from backend.parser_heuristics import parse_extracted_text
        
        # Simulated Hindi Appeal Memo with Grounds and Relief / Prayer sections
        hindi_appeal_text = (
            "--- PAGE 1 ---\n"
            "माननीय उच्च न्यायालय मध्यप्रदेश, जबलपुर\n"
            "विविध अपील क्रमांक 9876/2025\n"
            "राजेश कुमार विरुद्ध अनिल सिंह\n"
            "--- PAGE 2 ---\n"
            "अपील के आधार\n"
            "1. यह कि विद्वान दावा अधिकरण द्वारा पारित निर्णय दोषपूर्ण है।\n"
            "2. दावा अधिकरण ने मुआवजा राशि निर्धारण करने में भूल की है। मुआवजा राशि में वृद्धि की जाये।\n"
            "3. अवार्ड बढ़ाया जाये क्योंकि यह अत्यधिक कम और अत्यल्प क्षतिपूर्ति है।\n"
            "--- PAGE 3 ---\n"
            "प्रार्थना\n"
            "अतः सादर प्रार्थना है कि अपील स्वीकार की जावे। मुआवजा राशि में वृद्धि की जाये।\n"
            "न्यायोचित एवं समुचित क्षतिपूर्ति दिलाई जाये।"
        )
        
        lines = hindi_appeal_text.split("\n")
        suggestions = parse_extracted_text(lines)
        
        # Assertions
        case_classification = suggestions.get("case_classification", {})
        
        self.assertEqual(case_classification.get("verdict"), "enhancement")
        self.assertGreaterEqual(case_classification.get("confidence", 0.0), 0.70)
        
        # Verify grounds and relief snippets are extracted and not empty
        grounds_sig = case_classification.get("grounds_signal", {})
        relief_sig = case_classification.get("relief_signal", {})
        
        self.assertEqual(grounds_sig.get("verdict"), "enhancement")
        self.assertEqual(relief_sig.get("verdict"), "enhancement")
        self.assertTrue(bool(grounds_sig.get("snippet")))
        self.assertTrue(bool(relief_sig.get("snippet")))
        
        # Verify purna viram sentence boundary segmenting
        from backend.parser_heuristics import _extract_matching_points
        grounds_section_text = (
            "दावा अधिकरण ने मुआवजा राशि निर्धारण करने में भूल की है। मुआवजा राशि में वृद्धि की जाये।\n"
            "अवार्ड बढ़ाया जाये क्योंकि यह अत्यधिक कम और अत्यल्प क्षतिपूर्ति है।"
        )
        pts = _extract_matching_points(grounds_section_text, "enhancement")
        self.assertEqual(len(pts), 2)
        self.assertTrue(any("वृद्धि की जाये" in pt for pt in pts))
        self.assertTrue(any("अत्यल्प क्षतिपूर्ति" in pt for pt in pts))
        self.assertTrue(all("भूल की है" not in pt for pt in pts))

if __name__ == "__main__":
    unittest.main()
