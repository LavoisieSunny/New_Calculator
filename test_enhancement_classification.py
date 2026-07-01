import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.parser_heuristics import classify_enhancement_or_reduction


class TestEnhancementClassification(unittest.TestCase):

    def test_clear_enhancement_from_relief_section(self):
        sections = {
            "grounds_section": "The tribunal failed to consider future prospects properly.",
            "relief_section": "It is therefore prayed that the compensation be enhanced and just and proper compensation be awarded to the appellant."
        }
        result = classify_enhancement_or_reduction(sections)
        self.assertEqual(result["verdict"], "enhancement")
        self.assertGreater(result["confidence"], 0.0)
        self.assertEqual(result["basis"], "agreement" if result["grounds_signal"]["verdict"] == "enhancement" else "single_source")

    def test_clear_reduction_from_relief_section(self):
        sections = {
            "grounds_section": "The award granted is excessive and not supported by evidence.",
            "relief_section": "It is prayed that the impugned award be set aside and the amount be reduced."
        }
        result = classify_enhancement_or_reduction(sections)
        self.assertEqual(result["verdict"], "reduction")

    def test_conflicting_signals_not_determinable(self):
        sections = {
            "grounds_section": "The compensation awarded is excessive and ought to be reduced as the tribunal erred in computing future prospects.",
            "relief_section": "It is prayed that the compensation be enhanced and just compensation be granted to the claimant."
        }
        result = classify_enhancement_or_reduction(sections)
        self.assertEqual(result["verdict"], "not_determinable")
        self.assertEqual(result["basis"], "conflict")
        self.assertEqual(result["confidence"], 0.0)

    def test_no_signal_not_determinable(self):
        sections = {
            "grounds_section": "The deceased was 35 years old and employed as a driver earning Rs. 15,000 per month.",
            "relief_section": ""
        }
        result = classify_enhancement_or_reduction(sections)
        self.assertEqual(result["verdict"], "not_determinable")
        self.assertEqual(result["basis"], "no_signal")

    def test_past_tense_mention_does_not_count_as_signal(self):
        sections = {
            "grounds_section": "The tribunal correctly enhanced the award based on Pranay Sethi guidelines, but erred in the multiplier applied.",
            "relief_section": ""
        }
        result = classify_enhancement_or_reduction(sections)
        # "tribunal correctly enhanced" should be discounted as a past-tense
        # narrative statement, not a live prayer for enhancement.
        self.assertEqual(result["verdict"], "not_determinable")

    def test_relief_section_wins_when_grounds_has_no_signal(self):
        sections = {
            "grounds_section": "The deceased's income was wrongly computed by the tribunal.",
            "relief_section": "It is prayed that the compensation be enhanced."
        }
        result = classify_enhancement_or_reduction(sections)
        self.assertEqual(result["verdict"], "enhancement")
        self.assertEqual(result["basis"], "single_source")

    def test_snippet_does_not_cut_mid_word(self):
        sections = {
            "grounds_section": (
                "A. That the award of compensation passed by the learned Claims "
                "Tribunal is quite unjust, improper, insufficient and meagre, "
                "hence is liable to be enhanced in this appeal."
            ),
            "relief_section": (
                "(IX) RELIEF CLAIMED IN APPEAL : PRAYER 1. Enhancement of "
                "compensation by Rs. 2,00,000/- 2. Liability of insurer : "
                "Respondent No.3 3. Award of interest at the rate of 9% per annum."
            )
        }
        result = classify_enhancement_or_reduction(sections)
        grounds_snippet = result["grounds_signal"]["snippet"]
        relief_snippet = result["relief_signal"]["snippet"]

        # The excerpt may start/end with an ellipsis, but never with a
        # partial word fragment like "ms " or "sation ".
        for snippet in (grounds_snippet, relief_snippet):
            stripped = snippet.lstrip("…").rstrip("…").strip()
            self.assertTrue(stripped[0].isupper() or stripped[0].isdigit() or stripped[0] == "(",
                             f"Snippet appears to start mid-word: {snippet}")

    def test_bullet_points_extraction(self):
        sections = {
            "grounds_section": (
                "A. That the award of compensation passed by the learned Claims "
                "Tribunal is quite unjust, improper, insufficient and meagre, "
                "hence is liable to be enhanced in this appeal. B. The deceased "
                "was earning Rs. 15,000 per month."
            ),
            "relief_section": (
                "(IX) RELIEF CLAIMED IN APPEAL : PRAYER 1. Enhancement of "
                "compensation by Rs. 2,00,000/-. 2. Liability of insurer: Respondent No.3."
            )
        }
        result = classify_enhancement_or_reduction(sections)
        self.assertIn("grounds_points", result)
        self.assertIn("relief_points", result)
        self.assertIsInstance(result["grounds_points"], list)
        self.assertIsInstance(result["relief_points"], list)
        
        # Verify complete statements are returned (no mid-word or abbreviation truncation)
        self.assertTrue(any("liable to be enhanced" in p for p in result["grounds_points"]))
        self.assertTrue(any("Enhancement of compensation" in p for p in result["relief_points"]))


if __name__ == "__main__":
    unittest.main()
