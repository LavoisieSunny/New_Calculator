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

    def test_regression_fixtures(self):
        import os
        import json
        
        fixtures_dir = os.path.join(os.path.dirname(__file__), "tests", "fixtures", "lower_court")
        self.assertTrue(os.path.exists(fixtures_dir), f"Fixtures directory not found: {fixtures_dir}")
        
        files = [f for f in os.listdir(fixtures_dir) if f.endswith(".txt")]
        self.assertEqual(len(files), 11, f"Expected 11 fixture files, found {len(files)}")
        
        for f in files:
            name = os.path.splitext(f)[0]
            txt_path = os.path.join(fixtures_dir, f)
            json_path = os.path.join(fixtures_dir, f"{name}.json")
            
            with open(txt_path, "r", encoding="utf-8") as file:
                lines = [line.strip() for line in file.readlines() if line.strip()]
                
            with open(json_path, "r", encoding="utf-8") as file:
                expected = json.load(file)
                
            res = parse_hindi_extracted_text(lines)
            
            for field, expected_val in expected.items():
                actual_val = res.get(field, 0.0)
                self.assertEqual(
                    actual_val, expected_val,
                    f"Fixture {name}: Field '{field}' expected {expected_val}, got {actual_val}"
                )

    def test_new_hindi_biographical_fields(self):
        import os
        import json
        
        fixtures_dir = os.path.join(os.path.dirname(__file__), "tests", "fixtures", "lower_court")
        
        # 1. Test full MP-04 Style Form
        txt_path = os.path.join(fixtures_dir, "mp04_style_form.txt")
        with open(txt_path, "r", encoding="utf-8") as file:
            lines = [line.strip() for line in file.readlines() if line.strip()]
            
        res = parse_hindi_extracted_text(lines)
        
        self.assertEqual(res.get("injured_name"), "राजेश")
        self.assertEqual(res.get("father_name"), "रमेश")
        self.assertEqual(res.get("address"), "ग्राम चोरहटा, तहसील हुजूर, जिला रीवा, मध्य प्रदेश")
        self.assertEqual(res.get("age"), 35)
        self.assertEqual(res.get("occupation"), "निजी नौकरी")
        self.assertEqual(res.get("monthly_income"), 10000.0)
        self.assertEqual(res.get("date_of_accident"), "12.05.2025")
        self.assertEqual(res.get("place_of_accident"), "रीवा बाईपास, थाना चोरहटा, रीवा")
        self.assertEqual(res.get("injury_description"), "दाहिने पैर में फ्रैक्चर एवं सिर में गंभीर चोटें")
        self.assertEqual(res.get("vehicle_number"), "MP 17 AB 1234")
        self.assertEqual(res.get("hospital_name"), "संजय गांधी अस्पताल रीवा")
        self.assertEqual(res.get("driver_name"), "मोहन लाल")
        self.assertEqual(res.get("driver_address"), "ग्राम चोरहटा रीवा")
        self.assertEqual(res.get("owner_name"), "श्याम लाल")
        self.assertEqual(res.get("owner_address"), "विंध्य नगर रीवा")
        self.assertEqual(res.get("policy_number"), "1234567890/POL")
        self.assertEqual(res.get("insurance_company"), "न्यू इंडिया एश्योरेंस कंपनी लिमिटेड")
        self.assertEqual(res.get("is_income_tax_payer"), "नहीं")
        self.assertEqual(res.get("was_traveling_in_vehicle"), "नहीं")
        
        expected_breakdown = [
            {"label": "आर्थिक विकलांगता का प्रतिकर", "amount": 300000.0},
            {"label": "दुख दर्द व मानसिक परेशानी का प्रतिकर", "amount": 50000.0},
            {"label": "पथ्य आहार व आयागमन का व्यय", "amount": 40000.0},
            {"label": "ऑपरेशन एवं दवाई का खर्च", "amount": 100000.0},
            {"label": "कपड़ों की नुकसानी", "amount": 30000.0},
            {"label": "सहायक एवं अन्य व्यय", "amount": 20000.0},
            {"label": "भविष्य में होने वाली शारीरिक/इलाज खर्च", "amount": 200000.0},
            {"label": "कुल योग", "amount": 740000.0}
        ]
        self.assertEqual(res.get("compensation_claimed_breakdown"), expected_breakdown)
        
        expected_info = "दुर्घटना के समय वाहन चालक के पास वैध लायसेंस था।\nथाना चोरहटा में अपराध क्रमांक 111/2025 दर्ज है।\nवाहन का बीमा दुर्घटना दिनांक को वैध था।"
        self.assertEqual(res.get("other_case_info"), expected_info)
        self.assertEqual(res.get("fir_number"), "111/2025")
        self.assertEqual(res.get("police_station"), "थाना चोरहटा")
        
        # 2. Test Excerpt Form for Lookahead and other info Block Capture
        txt_path_excerpt = os.path.join(fixtures_dir, "other_info_excerpt.txt")
        with open(txt_path_excerpt, "r", encoding="utf-8") as file:
            lines_excerpt = [line.strip() for line in file.readlines() if line.strip()]
            
        res_excerpt = parse_hindi_extracted_text(lines_excerpt)
        self.assertEqual(res_excerpt.get("other_case_info"), expected_info)

    def test_document_a_lettered(self):
        text_lines = [
            "अ. स्थायी अपंगता हेतु क्षतिपूर्ति 5,00,000/-",
            "ब. शारीरिक एवं मानसिक वेदना 1,00,000",
            "स. चिकित्सा व्यय 4,00,000",
            "द. विशेष खुराक 50,000/-",
            "ध. परिचारक व रुकने वाले व्यक्ति का खर्च 50,000",
            "ऊ. भविष्य में होने वाले खर्च व आघात की हानि 2,00,000",
            "कुल योग 13,00,000/-"
        ]
        
        # Test Case 1: BUNDLED_FUTURE_TARGET_FIELD = "loss_of_income"
        with patch("backend.parser_heuristics.BUNDLED_FUTURE_TARGET_FIELD", "loss_of_income"):
            res = parse_hindi_extracted_text(text_lines)
            self.assertEqual(res.get("pain_and_suffering"), 600000.0) # 500000 + 100000
            self.assertEqual(res.get("medical_expenses"), 400000.0)
            self.assertEqual(res.get("special_diet"), 50000.0)
            self.assertEqual(res.get("attender_charges"), 50000.0)
            self.assertEqual(res.get("transportation"), 0.0)
            self.assertEqual(res.get("loss_of_income"), 200000.0)
            self.assertEqual(res.get("future_medical_expenses"), 0.0)

        # Test Case 2: BUNDLED_FUTURE_TARGET_FIELD = "future_medical_expenses"
        with patch("backend.parser_heuristics.BUNDLED_FUTURE_TARGET_FIELD", "future_medical_expenses"):
            res = parse_hindi_extracted_text(text_lines)
            self.assertEqual(res.get("pain_and_suffering"), 600000.0)
            self.assertEqual(res.get("medical_expenses"), 400000.0)
            self.assertEqual(res.get("special_diet"), 50000.0)
            self.assertEqual(res.get("attender_charges"), 50000.0)
            self.assertEqual(res.get("transportation"), 0.0)
            self.assertEqual(res.get("loss_of_income"), 0.0)
            self.assertEqual(res.get("future_medical_expenses"), 200000.0)

    def test_document_b_numbered(self):
        text_lines = [
            "1. स्थायी अपंगता हेतु क्षतिपूर्ति 3,00,000",
            "2. शारीरिक एवं मानसिक वेदना 50,000",
            "3. विशेष आहार एवं परिवहन व्यय 40,000",
            "4. इलाज व अस्पताल खर्च 1,00,000",
            "5. आवेदक जो नुकसानी का : 30,000/-",
            "6. परिचारक व्यय 20,000",
            "7. भविष्य में होने वाले व्यय व आघात की हानि 2,00,000",
            "कुल 7,40,000"
        ]
        
        # Test Case 1: BUNDLED_DIET_TRANSPORT_TARGET_FIELD = "special_diet"
        with patch("backend.parser_heuristics.BUNDLED_DIET_TRANSPORT_TARGET_FIELD", "special_diet"), \
             patch("backend.parser_heuristics.BUNDLED_FUTURE_TARGET_FIELD", "loss_of_income"):
            res = parse_hindi_extracted_text(text_lines)
            self.assertEqual(res.get("pain_and_suffering"), 350000.0) # 300000 + 50000
            self.assertEqual(res.get("special_diet"), 40000.0)
            self.assertEqual(res.get("transportation"), 0.0)
            self.assertEqual(res.get("medical_expenses"), 100000.0)
            self.assertEqual(res.get("attender_charges"), 20000.0)
            self.assertEqual(res.get("loss_of_income"), 200000.0)
            self.assertIn("5. आवेदक जो नुकसानी का : 30,000/-", res.get("needs_manual_review", []))

        # Test Case 2: BUNDLED_DIET_TRANSPORT_TARGET_FIELD = "transportation"
        with patch("backend.parser_heuristics.BUNDLED_DIET_TRANSPORT_TARGET_FIELD", "transportation"), \
             patch("backend.parser_heuristics.BUNDLED_FUTURE_TARGET_FIELD", "loss_of_income"):
            res = parse_hindi_extracted_text(text_lines)
            self.assertEqual(res.get("pain_and_suffering"), 350000.0)
            self.assertEqual(res.get("special_diet"), 0.0)
            self.assertEqual(res.get("transportation"), 40000.0)
            self.assertEqual(res.get("medical_expenses"), 100000.0)
            self.assertEqual(res.get("attender_charges"), 20000.0)
            self.assertEqual(res.get("loss_of_income"), 200000.0)
            self.assertIn("5. आवेदक जो नुकसानी का : 30,000/-", res.get("needs_manual_review", []))

    def test_document_c_biographical(self):
        text_lines = [
            "1. आवेदक का नाम व पिता का नाम : राजेश कुमार पुत्र श्री रमेश कुमार",
            "2. आवेदक का पूरा पता : जबलपुर, मध्य प्रदेश",
            "3. आवेदक की आयु : 35 वर्ष",
            "4. आवेदक का व्यवसाय : निजी नौकरी",
            "5. आवेदक की मासिक आय : 10,000/- रुपये प्रतिमाह",
            "6. घटना दिनांक, समय व स्थान : 12.05.2025 को जबलपुर",
            "7. घटना की रिपोर्ट किस थाने में : थाना कोतवाली में अपराध क्र 12/2025"
        ]
        
        res = parse_hindi_extracted_text(text_lines)
        
        # Verify it did NOT misfire as a damages table
        self.assertEqual(res.get("pain_and_suffering"), 0.0)
        self.assertEqual(res.get("medical_expenses"), 0.0)
        self.assertEqual(res.get("special_diet"), 0.0)
        
        # Verify biographical fields are populated correctly
        self.assertEqual(res.get("injured_name"), "राजेश")
        self.assertEqual(res.get("father_name"), "रमेश")
        self.assertEqual(res.get("age"), 35)
        self.assertEqual(res.get("monthly_income"), 10000.0)
        self.assertEqual(res.get("date_of_accident"), "12.05.2025")
        self.assertEqual(res.get("place_of_accident"), "जबलपुर")
        self.assertEqual(res.get("fir_number"), "12/2025")

    def test_self_insurance_and_vehicle_variants(self):
        text_lines = [
            "बीमा कंपनी : स्वयं",
            "वाहन क.-MP-20-BA-0911"
        ]
        res = parse_hindi_extracted_text(text_lines)
        self.assertEqual(res.get("insurance_company"), "स्वयं")
        self.assertEqual(res.get("vehicle_number"), "MP-20-BA-0911")

    def test_disability_proximity_guard_spacing_variants(self):
        # 39  प्रतिशत (double space)
        res1 = parse_hindi_extracted_text(["स्थायी अपंगता 39  प्रतिशत"], case_type="injury")
        self.assertEqual(res1.get("disability"), 39.0)
        
        # 39/प्रतिशत (slash separator)
        res2 = parse_hindi_extracted_text(["स्थायी अपंगता 39/प्रतिशत"], case_type="injury")
        self.assertEqual(res2.get("disability"), 39.0)
        
        # 39 % (space percent)
        res3 = parse_hindi_extracted_text(["स्थायी अपंगता 39 %"], case_type="injury")
        self.assertEqual(res3.get("disability"), 39.0)
        
        # List marker rejection (1. स्थायी अपंगता) - must be rejected and not trigger percentage
        res4 = parse_hindi_extracted_text(["1. स्थायी अपंगता", "2. मासिक आय 15000"], case_type="injury")
        self.assertIn(res4.get("disability"), ("", None))

    def test_plausibility_bound_rejection(self):
        from backend.parser_heuristics import check_amount_plausibility
        
        # Use assertLogs to verify that logger warning containing [SANITY-REJECT] is logged
        with self.assertLogs("ParserHeuristics", level="WARNING") as log_capture:
            # 1. Literal bad medical expenses value (11 digits)
            res1 = check_amount_plausibility(10023410743.0, "medical_expenses", "फ़ोन नंबर 10023410743")
            self.assertFalse(res1)
            
            # 2. Literal bad pain_and_suffering value (policy number matched as amount)
            res2 = check_amount_plausibility(45800311814000.0, "pain_and_suffering", "पालिसी नंबर 45800311814000")
            self.assertFalse(res2)
            
            # 3. An acceptable normal value
            res3 = check_amount_plausibility(50000.0, "special_diet", "विशेष खुराक व्यय 50,000")
            self.assertTrue(res3)
            
        self.assertEqual(len(log_capture.output), 2)
        self.assertIn("[SANITY-REJECT] field=medical_expenses rejected_value=10023410743.0 reason=exceeds_max_digits source_line='फ़ोन नंबर 10023410743'", log_capture.output[0])
        self.assertIn("[SANITY-REJECT] field=pain_and_suffering rejected_value=45800311814000.0 reason=exceeds_max_digits source_line='पालिसी नंबर 45800311814000'", log_capture.output[1])

    def test_document_a_lettered_real_world(self):
        text_lines = [
            "अ. स्थायी अपंगता हेतु क्षतिपूर्ति 5,00,000/-",
            "ब. शारीरिक एवं मानसिक वेदना 1,00,000",
            "स. चिकित्सा व्यय 4,00,000",
            "द. विशेष खुराक 50,000/-",
            "ध. परिचारक व रुकने वाले व्यक्ति का खर्च 50,000",
            "ऊ. भविष्य में होने वाले खर्च व आघात की हानि 2,00,000",
            "कुल योग 13,00,000/-",
            "18. अन्य जानकारी: वाहन क.-MP-20-BA-0911",
            "19. पालिसी नंबर 45800311814000",
            "20. फ़ोन नंबर 10023410743",
            "21. क्लेम नंबर 20NM/5566",
            "22. धारा 163{A}"
        ]
        
        res = parse_hindi_extracted_text(text_lines, case_type="injury")
        
        # Verify correct values are extracted
        self.assertEqual(res.get("pain_and_suffering"), 600000.0)  # 500000 disability + 100000 pain per merge rule
        self.assertEqual(res.get("medical_expenses"), 400000.0)
        self.assertEqual(res.get("special_diet"), 50000.0)
        self.assertEqual(res.get("attender_charges"), 50000.0)
        self.assertEqual(res.get("transportation"), 0.0)
        self.assertEqual(res.get("future_medical_expenses"), 200000.0)
        self.assertEqual(res.get("loss_of_income"), 0.0)
        
        # Verify disability percentage is None/empty (not mismatching to 1. from list markers)
        self.assertIn(res.get("disability"), ("", None))

    def test_decoy_blocks_and_anchor_scoring(self):
        text_lines = [
            # Decoy Block 1 (placed before the real table, lacks proper heading/end-anchor)
            "(1) इलाज खर्च : 10,000/-",
            "(2) पौष्टिक आहार : 5,000/-",
            "(3) आने जाने का व्यय : 2,000/-",
            "(4) दुख दर्द व मानसिक वेदना : 15,000/-",
            "(5) परिचारक व्यय : 3,000/-",
            "कुल : 35,000/-",
            
            "",
            # Real Block with "मुआवजे की राशि" heading variant
            "मुआवजे की राशि :--",
            "(1) स्थायी अपंगता का : 5,00,000/-",
            "(2) दुख दर्द व मानसिक वेदना : 1,00,000/-",
            "(3) पौष्टिक आहार : 25,000/-",
            "(4) इलाज व दवाई खर्च : 3,00,000/-",
            "(5) परिचारक व्यय : 50,000/-",
            "कुल : 9,75,000/-",
            # Typo'd/noisy end-anchor
            "१९. अन्य जानकरी जो निराकर के लिए आवश्क है",
            
            "",
            # Decoy Block 2 (placed after the real table, lacks proper heading/end-anchor)
            "(1) दवाई खर्च : 20,000/-",
            "(2) खुराक खर्च : 10,000/-",
            "(3) यातायात : 5,000/-",
            "(4) शारीरिक वेदना : 30,000/-",
            "(5) अटेंडेंट : 4,00,000/-",
            "कुल : 4,65,000/-"
        ]
        
        from backend.parser_heuristics import extract_hindi_structural_block
        res = extract_hindi_structural_block(text_lines)
        self.assertIsNotNone(res)
        
        # Verify that the scorer correctly prioritized the real block
        fields = res.get("fields", {})
        self.assertEqual(fields.get("pain_and_suffering"), 100000.0)
        self.assertEqual(fields.get("medical_expenses"), 300000.0)
        self.assertEqual(fields.get("special_diet"), 25000.0)
        self.assertEqual(fields.get("attender_charges"), 50000.0)

    def test_fuzzy_matching_adversarial(self):
        witness_statement = [
            "गवाह ने बयान दिया कि घटना दिनांक को वह मौके पर उपस्थित था।",
            "आरोपी ने 50000 रुपये की मांग की और गवाह से मारपीट की।",
            "पुलिस थाना सिविल लाइन्स में अपराध क्रमांक 123/26 दर्ज किया गया।",
            "चिकित्सक ने घायल राजेश का इलाज किया और दवाई का पर्चा दिया।"
        ]
        res = parse_hindi_extracted_text(witness_statement)
        self.assertEqual(res.get("pain_and_suffering", 0.0), 0.0)
        self.assertEqual(res.get("medical_expenses", 0.0), 0.0)
        self.assertEqual(res.get("special_diet", 0.0), 0.0)
        
    def test_confidence_and_needs_manual_review(self):
        text_high = [
            "मुआवजे की तालिका :--",
            "(1) इलाज व दवाई खर्च : 1,00,000/-",
            "(2) दुख दर्द व मानसिक वेदना : 50,000/-",
            "(3) पौष्टिक आहार : 10,000/-",
            "(4) परिचारक व्यय : 5,000/-",
            "(5) परिवहन व्यय : 5,000/-",
            "कुल : 1,70,000/-",
            "१९. अन्य जानकारी जो निराकरण के लिए आवश्यक है"
        ]
        res_high = parse_hindi_extracted_text(text_high)
        conf_high = res_high.get("confidence_scores", {})
        self.assertEqual(conf_high.get("medical_expenses", {}).get("confidence"), 0.96)
        self.assertEqual(conf_high.get("pain_and_suffering", {}).get("confidence"), 0.96)
        self.assertNotIn("Low anchor matching confidence for structural table block", res_high.get("needs_manual_review", []))

        text_med = [
            "(1) इलाज व दवाई खर्च : 1,00,000/-",
            "(2) दुख दर्द व मानसिक वेदना : 50,000/-",
            "(3) पौष्टिक आहार : 10,000/-",
            "(4) परिचारक व्यय : 5,000/-",
            "(5) परिवहन व्यय : 5,000/-",
            "कुल : 1,70,000/-",
            "१९. अन्य जानकारी जो निराकरण के लिए आवश्यक है"
        ]
        res_med = parse_hindi_extracted_text(text_med)
        conf_med = res_med.get("confidence_scores", {})
        self.assertEqual(conf_med.get("medical_expenses", {}).get("confidence"), 0.70)
        self.assertIn("needs_manual_review", res_med)
        self.assertTrue(any("missing heading lookback" in msg for msg in res_med["needs_manual_review"]))

        text_candidate = [
            "चिकित्सा खर्च रू 20,000/-"
        ]
        res_cand = parse_hindi_extracted_text(text_candidate)
        conf_cand = res_cand.get("confidence_scores", {})
        self.assertGreater(conf_cand.get("medical_expenses", {}).get("confidence", 0.0), 0.80)
        self.assertLessEqual(conf_cand.get("medical_expenses", {}).get("confidence", 0.0), 1.0)
        self.assertTrue(any("Felled back to candidate search logic" in msg for msg in res_cand.get("needs_manual_review", [])))

    def test_hindi_claim_form_compensation_mapping_and_confidence(self):
        text_lines = [
            "1. आवेदक का नाम व पिता का नाम : राजेश कुमार पुत्र श्री रमेश कुमार",
            "2. आवेदक का पूरा पता : जबलपुर, मध्य प्रदेश",
            "17. चाही गई मुआवजा राशि :-",
            "(1) आवेदिका को आई स्थाई अपंगता का : 2,00,000/-",
            "(2) दुख दर्द व मानसिक परेशानी का : 1,00,000/-",
            "(3) पौष्टिक आहार व आने जाने : 25,000/-",
            "(4) इलाज, आपरेशन व दवाई खर्च : 2,00,000/-",
            "(5) सहायक व्यय का खर्च : 25,000/-",
            "(6) भविष्य में होने वाली इलाज का : 2,00,000/-",
            "कुल : 7,50,000/-"
        ]
        
        res = parse_hindi_extracted_text(text_lines)
        
        # Verify mapped fields
        self.assertEqual(res.get("permanent_disability_amount"), 200000.0)
        self.assertEqual(res.get("pain_and_suffering"), 100000.0)
        self.assertEqual(res.get("special_diet"), 25000.0)
        self.assertEqual(res.get("transportation"), 0.0)  # Bundled target, other field gets 0
        self.assertEqual(res.get("medical_expenses"), 200000.0)
        self.assertEqual(res.get("attender_charges"), 25000.0)
        self.assertEqual(res.get("future_medical_expenses"), 200000.0)
        self.assertEqual(res.get("disability"), 0.0)  # Percentage field is set to 0 to prevent contamination
        
        # Verify duplicate amount confidence penalty (2,00,000 appears 3 times, 25,000 appears 2 times)
        conf_scores = res.get("confidence_scores", {})
        
        # permanent_disability_amount, medical_expenses, future_medical_expenses (amount 2,00,000)
        self.assertLess(conf_scores.get("permanent_disability_amount", {}).get("confidence", 1.0), 0.75)
        self.assertLess(conf_scores.get("medical_expenses", {}).get("confidence", 1.0), 0.75)
        self.assertLess(conf_scores.get("future_medical_expenses", {}).get("confidence", 1.0), 0.75)
        
        # special_diet, attender_charges, transportation (amount 25,000)
        self.assertLess(conf_scores.get("special_diet", {}).get("confidence", 1.0), 0.75)
        self.assertLess(conf_scores.get("attender_charges", {}).get("confidence", 1.0), 0.75)
        
        # Verify manual review alerts
        review_msgs = res.get("needs_manual_review", [])
        self.assertTrue(any("Multiple claim items share the same amount of 200000.00" in msg for msg in review_msgs))
        self.assertTrue(any("Multiple claim items share the same amount of 25000.00" in msg for msg in review_msgs))

if __name__ == "__main__":
    unittest.main()
