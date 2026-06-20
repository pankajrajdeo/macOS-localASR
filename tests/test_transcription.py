from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from macos_local_asr.transcription import (
    TranscriptionError,
    canonical_watch_url,
    default_output_path,
    download_url_to_media,
    download_url_to_wav,
    is_url,
    is_youtube_url,
    require_executable,
    summarize_downloader_error,
)


class TranscriptionHelperTests(unittest.TestCase):
    def test_is_url_accepts_http_urls_only(self) -> None:
        self.assertTrue(is_url("https://www.youtube.com/watch?v=abc"))
        self.assertTrue(is_url("http://example.com/audio.mp3"))
        self.assertFalse(is_url("/tmp/audio.mp3"))
        self.assertFalse(is_url("file:///tmp/audio.mp3"))

    def test_is_youtube_url_detects_common_hosts(self) -> None:
        self.assertTrue(is_youtube_url("https://www.youtube.com/watch?v=abc"))
        self.assertTrue(is_youtube_url("https://youtu.be/abc"))
        self.assertTrue(is_youtube_url("https://www.youtube-nocookie.com/embed/abc"))
        self.assertFalse(is_youtube_url("https://example.com/audio.mp3"))

    def test_canonical_watch_url_accepts_common_youtube_shapes(self) -> None:
        self.assertEqual(
            canonical_watch_url("https://www.youtube.com/watch?v=abc_123."),
            "https://www.youtube.com/watch?v=abc_123",
        )
        self.assertEqual(
            canonical_watch_url("https://youtu.be/abc-123?t=10"),
            "https://www.youtube.com/watch?v=abc-123",
        )
        self.assertEqual(
            canonical_watch_url("https://www.youtube.com/shorts/abc-123?feature=share"),
            "https://www.youtube.com/watch?v=abc-123",
        )
        self.assertIsNone(canonical_watch_url("https://example.com/watch?v=abc-123"))

    def test_default_output_path_for_file_and_url(self) -> None:
        self.assertEqual(default_output_path("/tmp/example/audio.wav"), Path("/tmp/example/transcript.txt"))
        self.assertEqual(default_output_path("https://example.com/audio.mp3"), Path.cwd() / "transcript.txt")

    def test_require_executable_reports_missing_binary(self) -> None:
        with patch("shutil.which", return_value=None):
            with self.assertRaisesRegex(TranscriptionError, "Missing required executable"):
                require_executable("definitely-not-installed")

    def test_downloader_error_is_summarized_for_gui(self) -> None:
        raw = "\n".join(
            [
                "WARNING: [youtube] YouTube said: ERROR - Precondition check failed.",
                "WARNING: [youtube] HTTP Error 400: Bad Request. Retrying (1/3)...",
                "WARNING: [youtube] Unable to download API page: HTTP Error 400: Bad Request",
            ]
        )
        self.assertIn("precondition-check failure", summarize_downloader_error(raw))

    def test_url_download_uses_temp_media_then_converts_to_wav(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = Path(tmp)
            output_path = temp_dir / "input.wav"

            media_path = temp_dir / "download.webm"
            media_path.write_bytes(b"temporary media")

            with patch("macos_local_asr.transcription.download_url_to_media", return_value=media_path), patch(
                "macos_local_asr.transcription.convert_to_wav"
            ) as convert:
                download_url_to_wav("https://example.com/video", output_path, 16000, temp_dir)

            convert.assert_called_once_with(temp_dir / "download.webm", output_path, 16000)

    def test_youtube_download_tries_mweb_before_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = Path(tmp)
            calls: list[tuple[str, dict[str, object]]] = []

            def fake_download(url: str, _temp_dir: Path, options: dict[str, object]) -> Path:
                calls.append((url, options))
                if len(calls) == 1:
                    raise TranscriptionError("first attempt failed")
                media_path = temp_dir / "download.webm"
                media_path.write_bytes(b"temporary media")
                return media_path

            with patch("macos_local_asr.transcription._download_with_ytdlp", side_effect=fake_download):
                media_path = download_url_to_media("https://youtu.be/abc-123?t=10", temp_dir)

            self.assertEqual(media_path, temp_dir / "download.webm")
            self.assertEqual(calls[0][0], "https://www.youtube.com/watch?v=abc-123")
            self.assertEqual(calls[1][0], "https://www.youtube.com/watch?v=abc-123")
            self.assertEqual(calls[0][1]["extractor_args"], {"youtube": {"player_client": ["mweb"]}})
            self.assertEqual(
                calls[1][1]["extractor_args"],
                {"youtube": {"player_client": ["default", "-android_sdkless"]}},
            )


if __name__ == "__main__":
    unittest.main()
