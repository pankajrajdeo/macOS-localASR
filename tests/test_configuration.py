from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from macos_local_asr.configuration import (
    DEFAULT_CONFIG,
    coerce_config_value,
    hotkey_label,
    parse_hotkey,
    set_config_value,
    validate_config,
)


class ConfigurationTests(unittest.TestCase):
    def test_hotkey_aliases_normalize(self) -> None:
        self.assertEqual(parse_hotkey("Command + Alt"), frozenset({"cmd", "option"}))
        self.assertEqual(parse_hotkey("control+cmd+option"), frozenset({"ctrl", "cmd", "option"}))
        self.assertEqual(hotkey_label(frozenset({"ctrl", "cmd", "option"})), "Control + Command + Option")

    def test_config_value_coercion(self) -> None:
        self.assertIs(coerce_config_value("preserve_clipboard", "off"), False)
        self.assertIs(coerce_config_value("preserve_clipboard", "true"), True)
        self.assertEqual(coerce_config_value("window_width", "240"), 240)
        self.assertEqual(coerce_config_value("vad_audible_rms", "0.01"), 0.01)

    def test_validation_rejects_unsupported_hotkey(self) -> None:
        config = dict(DEFAULT_CONFIG)
        config["hotkey"] = "cmd+shift"
        errors = validate_config(config)
        self.assertTrue(any("unsupported" in error for error in errors))

    def test_set_config_value_persists_valid_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.json"
            config = set_config_value("window_width", "250", path)
            self.assertEqual(config["window_width"], 250)
            self.assertIn('"window_width": 250', path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
