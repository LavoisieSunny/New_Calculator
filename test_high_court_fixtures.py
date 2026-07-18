import os
import json
import unittest
from backend.parser_heuristics import parse_extracted_text, detect_document_sections, classify_enhancement_or_reduction

def clean_spacing(s):
    if not s:
        return ""
    return " ".join(s.split())

class TestHighCourtFixtures(unittest.TestCase):
    def test_high_court_fixtures_regression(self):
        fixtures_dir = os.path.join(os.path.dirname(__file__), "tests", "fixtures", "high_court")
        self.assertTrue(os.path.exists(fixtures_dir), f"Fixtures directory not found: {fixtures_dir}")
        
        # Test the three main High Court files: ma_609, ma_2196, ma_10076, ma_3078
        files = ["ma_609", "ma_2196", "ma_10076", "ma_3078"]
        
        for name in files:
            txt_path = os.path.join(fixtures_dir, f"{name}.txt")
            json_path = os.path.join(fixtures_dir, f"{name}.json")
            
            self.assertTrue(os.path.exists(txt_path), f"Txt file not found: {txt_path}")
            self.assertTrue(os.path.exists(json_path), f"Json file not found: {json_path}")
            
            with open(txt_path, "r", encoding="utf-8") as f:
                lines = [line.rstrip() for line in f]
                
            with open(json_path, "r", encoding="utf-8") as f:
                expected = json.load(f)
                
            # 1. Segment lines into pages exactly as parse_extracted_text does
            pages = []
            current_page_num = 1
            current_page_lines = []
            for line in lines:
                if line.strip().startswith("--- PAGE"):
                    if current_page_lines:
                        pages.append({
                            "page_number": current_page_num,
                            "lines": current_page_lines,
                            "text": "\n".join(current_page_lines)
                        })
                    current_page_lines = []
                    import re
                    m = re.search(r'PAGE\s+(\d+)', line, re.IGNORECASE)
                    if m:
                        current_page_num = int(m.group(1))
                else:
                    current_page_lines.append(line)
            if current_page_lines or not pages:
                pages.append({
                    "page_number": current_page_num,
                    "lines": current_page_lines,
                    "text": "\n".join(current_page_lines)
                })
                
            full_text = "\n".join(lines)
            
            # 2. Extract sections using detect_document_sections
            sections_meta = detect_document_sections(full_text, pages)
            sections = {k: v["content"] for k, v in sections_meta.items()}
            sections["raw_ocr"] = full_text
            
            # 3. Assert facts_section exists and contains expected narrative facts/grievance
            facts_content = clean_spacing(sections.get("facts_section", ""))
            self.assertTrue(facts_content, f"Fixture {name}: facts_section not found or empty")
            for sub in expected["facts_section_contains"]:
                clean_sub = clean_spacing(sub)
                self.assertIn(clean_sub, facts_content, f"Fixture {name}: facts_section does not contain '{sub}'")
                
            # 4. Assert grounds_section exists and matches lettered/numbered grounds (not just heading line)
            grounds_content = clean_spacing(sections.get("grounds_section", ""))
            self.assertTrue(grounds_content, f"Fixture {name}: grounds_section not found or empty")
            for sub in expected["grounds_section_contains"]:
                clean_sub = clean_spacing(sub)
                self.assertIn(clean_sub, grounds_content, f"Fixture {name}: grounds_section does not contain '{sub}'")
                
            # 5. Assert relief_section / prayer content exists and matches prayer clauses under (IX)
            relief_content = clean_spacing(sections.get("relief_section", ""))
            self.assertTrue(relief_content, f"Fixture {name}: relief_section not found or empty")
            for sub in expected["relief_section_contains"]:
                clean_sub = clean_spacing(sub).replace("é", "e")
                cleaned_relief = relief_content.replace("é", "e")
                self.assertIn(clean_sub, cleaned_relief, f"Fixture {name}: relief_section does not contain '{sub}'")
                
            # 6. Verify classify_enhancement_or_reduction classification and "agreement" basis
            verdict = classify_enhancement_or_reduction(sections)
            expected_class = expected["classification"]
            self.assertEqual(verdict["verdict"], expected_class["verdict"], f"Fixture {name}: expected verdict {expected_class['verdict']}, got {verdict['verdict']}")
            self.assertEqual(verdict["basis"], expected_class["basis"], f"Fixture {name}: expected basis {expected_class['basis']}, got {verdict['basis']}")

            # 7. Genuine Heuristics Validation: Assert parsed fields match ground truth without AI recovery mocks
            if "ground_truth" in expected:
                gt = expected["ground_truth"]
                suggestions = parse_extracted_text(lines)
                
                # Assert Name of Deceased
                if "deceased_name" in gt:
                    self._assert_field_match(suggestions.get("name") or suggestions.get("deceased_name"), gt["deceased_name"], f"{name}: name")
                
                # Assert Father/Husband Name
                if "father_name" in gt:
                    self._assert_field_match(suggestions.get("father_name"), gt["father_name"], f"{name}: father_name")
                
                # Assert Date of Accident
                if "date_of_accident" in gt:
                    self._assert_field_match(suggestions.get("date_of_accident"), gt["date_of_accident"], f"{name}: date_of_accident")
                
                # Assert Place of Accident
                if "place_of_accident" in gt:
                    self._assert_field_match(suggestions.get("place_of_accident"), gt["place_of_accident"], f"{name}: place_of_accident")
                
                # Assert Age
                if "age" in gt:
                    self._assert_field_match(suggestions.get("age"), gt["age"], f"{name}: age")
                
                # Assert Monthly Income
                if "monthly_income" in gt:
                    self._assert_field_match(suggestions.get("monthly_income"), gt["monthly_income"], f"{name}: monthly_income", tolerance=10.0)
                
                # Assert Marital Status
                if "marital_status" in gt:
                    self._assert_field_match(suggestions.get("marital_status"), gt["marital_status"], f"{name}: marital_status")
                
                # Assert Future Prospects Type
                if "future_type" in gt:
                    self._assert_field_match(suggestions.get("future_type"), gt["future_type"], f"{name}: future_type")

    def _assert_field_match(self, extracted, expected, field_name, tolerance=None):
        if isinstance(expected, list):
            match_found = False
            for exp in expected:
                try:
                    if tolerance is not None and extracted is not None and exp is not None:
                        if abs(float(extracted) - float(exp)) <= tolerance:
                            match_found = True
                            break
                    else:
                        if str(extracted).strip().lower() == str(exp).strip().lower() if extracted is not None and exp is not None else (extracted in (None, "") and exp in (None, "")):
                            match_found = True
                            break
                except (ValueError, TypeError):
                    if str(extracted).strip().lower() == str(exp).strip().lower() if extracted is not None and exp is not None else (extracted in (None, "") and exp in (None, "")):
                            match_found = True
                            break
            self.assertTrue(
                match_found, 
                f"Field '{field_name}' got '{extracted}', expected one of {expected}"
            )
        else:
            if tolerance is not None:
                self.assertIsNotNone(extracted, f"Field '{field_name}' is None, expected {expected}")
                self.assertAlmostEqual(float(extracted), float(expected), delta=tolerance, msg=f"Field '{field_name}' mismatch")
            else:
                self.assertEqual(
                    str(extracted).strip().lower() if extracted is not None else "",
                    str(expected).strip().lower() if expected is not None else "",
                    f"Field '{field_name}' mismatch"
                )

if __name__ == "__main__":
    unittest.main()
