import json
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pii_ai_functions import mask_response


class MaskTests(unittest.TestCase):
    def test_repeated_overlapping_values_and_unchanged_surroundings(self):
        text = "ID AB123; ID AB123; ticket INC-48271."
        result = mask_response(text, json.dumps({"entities": [
            {"text": "AB123", "category": "ID"},
            {"text": "AB12", "category": "ID"},
        ]}))
        self.assertEqual(result["redacted"], "ID *****; ID *****; ticket INC-48271.")

    def test_empty_detection_is_not_a_safety_claim(self):
        self.assertEqual(mask_response("visible", '{"entities": []}')["redacted"], "visible")

    def test_rejects_normalization_and_hallucination(self):
        with self.assertRaises(ValueError):
            mask_response("AB 123", '{"entities":[{"text":"AB123","category":"ID"}]}')

    def test_rejects_invalid_structure(self):
        for response in ['null', '{"entities": null}', '{"entities":[{}]}',
                         '{"entities":[{"text":"","category":"ID"}]}']:
            with self.subTest(response=response), self.assertRaises(ValueError):
                mask_response("text", response)


if __name__ == "__main__":
    unittest.main()
