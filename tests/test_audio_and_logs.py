from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import numpy as np

from macos_local_asr.configuration import DEFAULT_CONFIG
from macos_local_asr.daemon import rotate_log_if_needed, trim_audio_with_vad


class AudioAndLogTests(unittest.TestCase):
    def test_vad_skips_silent_audio(self) -> None:
        config = dict(DEFAULT_CONFIG)
        audio = np.zeros(16000, dtype=np.float32)
        trimmed, stats = trim_audio_with_vad(audio, 16000, config)
        self.assertIsNone(trimmed)
        self.assertEqual(stats.reason, "below_rms_floor")

    def test_vad_disabled_returns_original_audio(self) -> None:
        config = dict(DEFAULT_CONFIG)
        config["vad_enabled"] = False
        audio = np.linspace(-0.01, 0.01, 1600, dtype=np.float32)
        trimmed, stats = trim_audio_with_vad(audio, 16000, config)
        self.assertIsNotNone(trimmed)
        np.testing.assert_array_equal(trimmed, audio)
        self.assertEqual(stats.reason, "disabled")

    def test_log_rotation_keeps_backups(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "daemon.log"
            path.write_text("x" * 100, encoding="utf-8")

            original = __import__("macos_local_asr.daemon", fromlist=["load_log_rotation_settings"])
            old_settings = original.load_log_rotation_settings
            try:
                original.load_log_rotation_settings = lambda: (50, 2)
                rotate_log_if_needed(path)
            finally:
                original.load_log_rotation_settings = old_settings

            self.assertFalse(path.exists())
            self.assertTrue((Path(tmpdir) / "daemon.log.1").exists())


if __name__ == "__main__":
    unittest.main()
