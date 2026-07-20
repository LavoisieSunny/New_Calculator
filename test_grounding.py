import unittest
from backend.llm_client import _verify_summary_grounding

class TestGroundingCheck(unittest.TestCase):
    def test_grounding_verification(self):
        source = "The claimant filed an appeal seeking Rs. 2,00,000 enhancement and 9% interest."
        
        # 1. Grounding check passes when all numbers are in source
        valid_summary = {
            "case_overview": "Claimant is seeking enhancement.",
            "appeal_direction": "enhancement",
            "grounds_of_appeal": ["The appellant claims 9% interest is justified."],
            "relief_sought": ["Please grant an enhancement of Rs. 200000."],
            "key_figures_cited": ["₹2,00,000 enhancement sought", "9% interest claimed"],
            "confidence": 0.95
        }
        
        verified = _verify_summary_grounding(valid_summary, source)
        self.assertEqual(len(verified["key_figures_cited"]), 2)
        self.assertNotIn("[figure unverified]", verified["grounds_of_appeal"][0])
        self.assertNotIn("[figure unverified]", verified["relief_sought"][0])
        
        # 2. Grounding check drops/rewrites when figures are not in source
        invalid_summary = {
            "case_overview": "Claimant is seeking enhancement.",
            "appeal_direction": "enhancement",
            "grounds_of_appeal": ["The appellant claims 18% interest is justified."], # 18 is not in source
            "relief_sought": ["Please grant an enhancement of Rs. 500000."], # 500000 is not in source
            "key_figures_cited": ["₹5,00,000 enhancement sought", "18% interest claimed"],
            "confidence": 0.95
        }
        
        verified_invalid = _verify_summary_grounding(invalid_summary, source)
        self.assertEqual(len(verified_invalid["key_figures_cited"]), 0) # both dropped
        self.assertIn("[figure unverified]", verified_invalid["grounds_of_appeal"][0])
        self.assertIn("[figure unverified]", verified_invalid["relief_sought"][0])

if __name__ == "__main__":
    unittest.main()
