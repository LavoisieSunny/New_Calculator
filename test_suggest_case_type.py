import unittest
from fastapi.testclient import TestClient
from backend.main import app

class TestSuggestCaseType(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_suggest_case_type_endpoint(self):
        payload = {
            "raw_text": "This is a case of fatal accident where the deceased died on the spot.",
            "selected_case_type": "death"
        }
        response = self.client.post("/api/ocr/suggest-case-type", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("suggestions", data)
        self.assertIn("selected", data)
        self.assertEqual(data["selected"], "death")
        
        # Verify format of suggestions
        suggestions = data["suggestions"]
        self.assertGreater(len(suggestions), 0)
        for s in suggestions:
            self.assertIn("case_type", s)
            self.assertIn("confidence", s)
            self.assertIsInstance(s["confidence"], (int, float))

    def test_suggest_case_type_hindi_injury(self):
        from backend.llm_client import classify_case_type_by_ocr_text
        bhopal_injury_text = (
            "अधिकरण भोपाल (म.प्र.)\n"
            "मोटर दुर्घटना दावा क्रमांक 123/2024\n"
            "आवेदक को दुर्घटना में स्थायी अपंगता (Permanent Disability) कारित हुई है।\n"
            "चिकित्सा बोर्ड ने आवेदक की स्थायी निःशक्तता 40 प्रतिशत निर्धारित की है।\n"
            "आवेदक को शारीरिक एवं मानसिक वेदना के लिए प्रतिकर दिया जाता है।"
        )
        self.assertEqual(classify_case_type_by_ocr_text(bhopal_injury_text), "injury")

    def test_suggest_case_type_hindi_death(self):
        from backend.llm_client import classify_case_type_by_ocr_text
        rewa_death_text = (
            "दावा अधिकरण रीवा (म.प्र.)\n"
            "दुर्घटना में मृतक सुरेश का देहांत हो गया।\n"
            "मृतक की मृत्यु के कारण उसके वैध वारिस (विधवा एवं बच्चे) आश्रित हैं।\n"
            "अत: मृतक की मृत्यु के संबंध में प्रतिकर का निर्धारण निम्नानुसार किया जाता है:\n"
            "स्वर्गीय सुरेश की आयु दुर्घटना के समय 35 वर्ष थी।"
        )
        self.assertEqual(classify_case_type_by_ocr_text(rewa_death_text), "death")

if __name__ == "__main__":
    unittest.main()
