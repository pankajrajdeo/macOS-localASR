from __future__ import annotations

import unittest
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from macos_local_asr.daemon import capture_clipboard, restore_clipboard, set_clipboard

try:
    from AppKit import NSPasteboard, NSPasteboardTypeString
except Exception:  # noqa: BLE001
    NSPasteboard = None
    NSPasteboardTypeString = None


@unittest.skipIf(NSPasteboard is None, "AppKit pasteboard unavailable")
class ClipboardTests(unittest.TestCase):
    def test_clipboard_snapshot_restores_previous_text(self) -> None:
        pasteboard = NSPasteboard.generalPasteboard()
        original = capture_clipboard()
        try:
            set_clipboard("macos-local-asr-before")
            snapshot = capture_clipboard()
            set_clipboard("macos-local-asr-after")
            restore_clipboard(snapshot)
            restored = str(pasteboard.stringForType_(NSPasteboardTypeString) or "")
            self.assertEqual(restored, "macos-local-asr-before")
        finally:
            restore_clipboard(original)


if __name__ == "__main__":
    unittest.main()
