"""Mocked tests for clef-decide. No network, no key, no charges.

Run: python3 -m pytest tests/  (or python3 tests/test_clef_mock.py)
"""
import io
import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))
import importlib.util
import importlib.machinery
spec = importlib.util.spec_from_file_location(
    "clef_decide",
    os.path.join(os.path.dirname(__file__), "..", "bin", "clef-decide"),
    loader=importlib.machinery.SourceFileLoader("clef_decide",
        os.path.join(os.path.dirname(__file__), "..", "bin", "clef-decide")))
clef = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clef)

CANNED = {
    "model": "clef-1.0.0",
    "answers": {
        "review": {
            "type": "choice",
            "choice": "review",
            "confidence": 0.81,
            "probabilities": {"accept": 0.19, "review": 0.81},
        },
        "risk": {
            "type": "score",
            "score": 1.0,
            "confidence": 0.9,
            "legend": {"0": "none", "1": "low", "2": "high"},
            "probabilities": {"0": 0.1, "1": 0.9, "2": 0.0},
        },
        "urgent": {"type": "noul", "noul": 0.0},
    },
    "usage": {"input_tokens": 120, "output_tokens": 40},
}


class FakeResp:
    def __init__(self, payload):
        self._payload = payload
    def read(self):
        return json.dumps(self._payload).encode()
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def make_opener(captured):
    def opener(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["auth"] = req.get_header("Authorization")
        captured["ctype"] = req.get_header("Content-type")
        captured["body"] = json.loads(req.data.decode())
        captured["timeout"] = timeout
        return FakeResp(CANNED)
    return opener


QUESTIONS = {
    "review": {"type": "choice", "instructions": "Accept or request review?",
               "criteria": {"accept": "safe to merge", "review": "needs human eyes"}},
    "risk": {"type": "score", "instructions": "Risk level?",
             "criteria": ["none", "low", "high"]},
    "urgent": {"type": "noul", "instructions": "Is this urgent?"},
}


class TestClefDecide(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"EXPERIENTIAL_API_KEY": "test-key-dummy"})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_request_shape(self):
        cap = {}
        payload, est = clef.call_clef("clef", "diff summary here", QUESTIONS,
                                     _opener=make_opener(cap))
        self.assertEqual(cap["url"], "https://api.experientiallabs.ai/v1/systemone")
        self.assertEqual(cap["method"], "POST")
        self.assertEqual(cap["auth"], "Bearer test-key-dummy")
        self.assertEqual(cap["ctype"], "application/json")
        self.assertEqual(cap["body"]["model"], "clef")
        self.assertEqual(cap["body"]["state"], "diff summary here")
        self.assertEqual(set(cap["body"]["questions"]), {"review", "risk", "urgent"})
        self.assertEqual(cap["timeout"], 60)
        # no idempotency key header
        self.assertIsNone(cap.get("idem"))

    def test_free_spelling_preserved(self):
        cap = {}
        clef.call_clef("clef:free", "s", QUESTIONS, _opener=make_opener(cap))
        self.assertEqual(cap["body"]["model"], "clef:free")

    def test_non_clef_model_rejected(self):
        with self.assertRaises(clef.ClefError):
            clef.call_clef("gpt-4", "s", QUESTIONS, _opener=make_opener({}))

    def test_answers_by_id_and_usage(self):
        cap = {}
        payload, _ = clef.call_clef("clef", "s", QUESTIONS, _opener=make_opener(cap))
        self.assertEqual(payload["answers"]["review"]["choice"], "review")
        self.assertEqual(payload["answers"]["risk"]["score"], 1.0)
        self.assertEqual(payload["answers"]["urgent"]["noul"], 0.0)
        self.assertEqual(payload["usage"]["input_tokens"], 120)
        human = clef.render_human(payload)
        self.assertIn("[review] choice -> review", human)
        self.assertIn("input_tokens=120", human)

    def test_missing_key_stops(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(clef.ClefError) as cm:
                clef.call_clef("clef", "s", QUESTIONS, _opener=make_opener({}))
        self.assertIn("EXPERIENTIAL_API_KEY", str(cm.exception))

    def test_context_budget_refuses(self):
        big = "x" * (16384 * 4 + 100)
        with self.assertRaises(clef.ClefError) as cm:
            clef.call_clef("clef", big, QUESTIONS, _opener=make_opener({}))
        self.assertIn("16384", str(cm.exception))

    def test_gateway_bounds(self):
        many = {f"q{i}": {"type": "noul", "instructions": "x"} for i in range(33)}
        with self.assertRaises(clef.ClefError):
            clef.call_clef("clef", "s", many, _opener=make_opener({}))
        wide = {"q": {"type": "choice", "instructions": "x",
                      "criteria": {f"o{i}": "d" for i in range(65)}}}
        with self.assertRaises(clef.ClefError):
            clef.call_clef("clef", "s", wide, _opener=make_opener({}))
        flat = {"q": {"type": "score", "instructions": "x", "criteria": ["only"]}}
        with self.assertRaises(clef.ClefError):
            clef.call_clef("clef", "s", flat, _opener=make_opener({}))

    def test_http_error_surfaces(self):
        import urllib.error
        def boom(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 402, "Payment Required", {}, io.BytesIO(b"no credit"))
        with self.assertRaises(clef.ClefError) as cm:
            clef.call_clef("clef", "s", QUESTIONS, _opener=boom)
        self.assertIn("402", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
