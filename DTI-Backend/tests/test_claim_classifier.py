import os
import sys
import unittest
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
research_dir = backend_dir.parent / "research" / "research"
sys.path.insert(0, str(research_dir))

from text_verification.claim_processing.claim_classifier import ClaimClassifier


class TestClaimClassifier(unittest.TestCase):
    def test_opinion_classification(self):
        claims = [
            "In my opinion this is the greatest album ever made.",
            "I believe this movie is terrible and overrated.",
            "This city is the most beautiful place in the world."
        ]
        for c in claims:
            claim_type, is_verifiable, reason = ClaimClassifier.classify(c)
            self.assertEqual(claim_type, "opinion")
            self.assertFalse(is_verifiable)
            self.assertIn("opinion", reason.lower())

    def test_prediction_classification(self):
        claims = [
            "Global temperatures will surpass 2.0 degrees by 2040.",
            "Electric vehicles are expected to replace gas cars by 2050.",
            "This company will become the largest tech firm in the future."
        ]
        for c in claims:
            claim_type, is_verifiable, reason = ClaimClassifier.classify(c)
            self.assertEqual(claim_type, "prediction")
            self.assertFalse(is_verifiable)

    def test_numeric_classification(self):
        claims = [
            "Renewable energy production surged by 50% in 2023.",
            "The national deficit reached $1.7 trillion this quarter.",
            "The company increased revenue by 25 percent."
        ]
        for c in claims:
            claim_type, is_verifiable, _ = ClaimClassifier.classify(c)
            self.assertEqual(claim_type, "numeric")
            self.assertTrue(is_verifiable)

    def test_scientific_classification(self):
        claims = [
            "NASA confirms new ice deposits detected by lunar orbiter.",
            "James Webb Space Telescope detects carbon dioxide on exoplanet."
        ]
        for c in claims:
            claim_type, is_verifiable, _ = ClaimClassifier.classify(c)
            self.assertEqual(claim_type, "scientific")
            self.assertTrue(is_verifiable)

    def test_medical_classification(self):
        claims = [
            "FDA approves breakthrough mRNA vaccine for pancreatic cancer.",
            "Clinical trial reports 90% efficacy for new malaria treatment."
        ]
        for c in claims:
            claim_type, is_verifiable, _ = ClaimClassifier.classify(c)
            self.assertEqual(claim_type, "medical")
            self.assertTrue(is_verifiable)

    def test_non_verifiable_classification(self):
        claims = [
            "What should we do about the weather?",
            "How to fix a sink?",
            "Hi"
        ]
        for c in claims:
            claim_type, is_verifiable, _ = ClaimClassifier.classify(c)
            self.assertEqual(claim_type, "non_verifiable")
            self.assertFalse(is_verifiable)


if __name__ == "__main__":
    unittest.main()
