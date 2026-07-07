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

if __name__ == "__main__":
    unittest.main()
