import unittest
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ghostkeep.sieve import MemorySieve
from ghostkeep.scribe import MemoryScribe


class TestMemorySieveAndScribe(unittest.TestCase):
    def setUp(self):
        self.sieve = MemorySieve()
        self.scribe = MemoryScribe()

    def test_ephemeral_noise_discarded(self):
        noisy_inputs = [
            "npm test: 24 passed, 0 failed",
            "git status: on branch main",
            "hello",
            "thanks, got it!",
            "downloading dependencies: 45% cached",
        ]
        for inp in noisy_inputs:
            res = self.sieve.evaluate(inp)
            self.assertFalse(res.is_durable, f"Expected noise to be discarded: {inp}")

    def test_durable_decision_captured(self):
        decision_input = "We decided to switch from PyTorch to ONNX Runtime because memory footprint was 4x lower"
        res = self.sieve.evaluate(decision_input)
        self.assertTrue(res.is_durable)
        self.assertGreaterEqual(res.confidence, 0.75)

        distilled = self.scribe.distill(decision_input, res)
        self.assertTrue(len(distilled["content"]) > 10)
        self.assertEqual(distilled["confidence"], res.confidence)

    def test_constraint_detected_with_domain(self):
        constraint_input = "Constraint: Always use Vanilla CSS for styling components instead of Tailwind"
        res = self.sieve.evaluate(constraint_input)
        self.assertTrue(res.is_durable)
        self.assertEqual(res.domain, "ui")

        distilled = self.scribe.distill(constraint_input, res)
        self.assertIn("ui", distilled["tags"])
        self.assertIn("css", distilled["tags"])


if __name__ == "__main__":
    unittest.main()
