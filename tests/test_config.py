"""Tests for standard key/endpoint configuration.

Precedence: --api-key flag > $CLEF_API_KEY > $EXPERIENTIAL_API_KEY (legacy)
> config file. Endpoint: flag > $CLEF_ENDPOINT > config file > default.
Fully mocked — no network, no key, no charges.

Run: python3 -m unittest tests.test_config
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
BIN_PATH = os.path.join(REPO_ROOT, "bin", "clef-decide")

import importlib.util
import importlib.machinery
spec = importlib.util.spec_from_file_location(
    "clef_decide_cfg",
    BIN_PATH,
    loader=importlib.machinery.SourceFileLoader("clef_decide_cfg", BIN_PATH))
clef = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clef)


def write_config(content):
    fd, path = tempfile.mkstemp(prefix="clef-test-", suffix=".conf")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return path


class TestKeyPrecedence(unittest.TestCase):
    def test_flag_beats_everything(self):
        cfg = write_config("api_key=config-key\n")
        try:
            with patch.dict(os.environ, {"CLEF_API_KEY": "env-key",
                                         "EXPERIENTIAL_API_KEY": "legacy-key"}):
                self.assertEqual(
                    clef.resolve_key(flag_value="flag-key", config_path=cfg),
                    "flag-key")
        finally:
            os.unlink(cfg)

    def test_clef_env_beats_legacy_env(self):
        with patch.dict(os.environ, {"CLEF_API_KEY": "env-key",
                                     "EXPERIENTIAL_API_KEY": "legacy-key"}):
            self.assertEqual(clef.resolve_key(config_path="/nonexistent"), "env-key")

    def test_legacy_env_still_honored(self):
        with patch.dict(os.environ, {"EXPERIENTIAL_API_KEY": "legacy-key"}, clear=False):
            env = {"EXPERIENTIAL_API_KEY": "legacy-key"}
            with patch.dict(os.environ, env, clear=True):
                self.assertEqual(clef.resolve_key(config_path="/nonexistent"),
                                 "legacy-key")

    def test_config_file_used_when_no_env(self):
        cfg = write_config("# comment\napi_key = \"config-key\" \n")
        try:
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(clef.resolve_key(config_path=cfg), "config-key")
        finally:
            os.unlink(cfg)

    def test_missing_everywhere_stops_with_setup_help(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(clef.ClefError) as cm:
                clef.resolve_key(config_path="/nonexistent")
        msg = str(cm.exception)
        self.assertIn("--api-key", msg)
        self.assertIn("CLEF_API_KEY", msg)
        self.assertIn("EXPERIENTIAL_API_KEY", msg)
        self.assertIn("config", msg)

    def test_config_parsing_ignores_junk(self):
        cfg = write_config("garbage line\n# comment\n\napi_key='q-key'\nendpoint = https://x.example/v1\n")
        try:
            parsed = clef.read_config_file(cfg)
            self.assertEqual(parsed, {"api_key": "q-key",
                                      "endpoint": "https://x.example/v1"})
        finally:
            os.unlink(cfg)

    def test_missing_config_file_is_empty(self):
        self.assertEqual(clef.read_config_file("/nonexistent"), {})


class TestEndpointResolution(unittest.TestCase):
    def test_default_endpoint(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(clef.resolve_endpoint(config_path="/nonexistent"),
                             clef.ENDPOINT)

    def test_flag_endpoint(self):
        self.assertEqual(
            clef.resolve_endpoint(flag_value="https://ep.example/v1",
                                  config_path="/nonexistent"),
            "https://ep.example/v1")

    def test_env_endpoint(self):
        with patch.dict(os.environ, {"CLEF_ENDPOINT": "https://env.example/v1"}):
            self.assertEqual(clef.resolve_endpoint(config_path="/nonexistent"),
                             "https://env.example/v1")

    def test_config_endpoint(self):
        cfg = write_config("endpoint=https://cfg.example/v1\n")
        try:
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(clef.resolve_endpoint(config_path=cfg),
                                 "https://cfg.example/v1")
        finally:
            os.unlink(cfg)

    def test_non_https_endpoint_rejected(self):
        with self.assertRaises(clef.ClefError):
            clef.resolve_endpoint(flag_value="http://insecure.example/v1",
                                  config_path="/nonexistent")


if __name__ == "__main__":
    unittest.main()
