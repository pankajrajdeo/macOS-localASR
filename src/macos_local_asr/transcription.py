from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import onnx_asr

from .cleanup import CleanupError, cleanup_text
from .configuration import MODEL_DIR


class TranscriptionError(RuntimeError):
    pass


_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}
_YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{3,}$")


class _SilentYtdlpLogger:
    def debug(self, _message: str) -> None:
        return

    def info(self, _message: str) -> None:
        return

    def warning(self, _message: str) -> None:
        return

    def error(self, _message: str) -> None:
        return


@dataclass(frozen=True)
class TranscriptionResult:
    source: str
    output_path: Path
    text: str
    raw_text: str
    audio_sec: float | None
    asr_latency_sec: float
    cleanup_latency_sec: float


def is_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_youtube_url(value: str) -> bool:
    host = (urlparse(value.strip()).hostname or "").lower()
    return host in _YOUTUBE_HOSTS or host == "youtu.be"


def canonical_watch_url(url: str) -> str | None:
    video_id = _extract_video_id(url)
    if not video_id:
        return None
    return f"https://www.youtube.com/watch?v={video_id}"


def _extract_video_id(url: str) -> str | None:
    raw = (url or "").strip().strip("<>[](){}\"'")
    raw = raw.rstrip(".,;")
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    query = parse_qs(parsed.query)
    is_known_youtube_host = host in _YOUTUBE_HOSTS or host == "youtu.be"

    if is_known_youtube_host:
        for key in ("v", "vi"):
            video_id = _clean_video_id(query.get(key, [""])[0])
            if video_id:
                return video_id

    path_parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
    if host == "youtu.be" and path_parts:
        return _clean_video_id(path_parts[0])

    if host not in _YOUTUBE_HOSTS:
        return None

    if len(path_parts) >= 2 and path_parts[0].lower() in {"embed", "e", "live", "shorts", "v", "watch"}:
        video_id = _clean_video_id(path_parts[1])
        if video_id:
            return video_id

    for key in ("u", "q", "url"):
        for nested in query.get(key, []):
            nested_url = urljoin("https://www.youtube.com", unquote(nested))
            nested_id = _extract_video_id(nested_url)
            if nested_id:
                return nested_id
    return None


def _clean_video_id(value: str | None) -> str | None:
    cleaned = (value or "").strip().strip("<>[](){}\"'")
    cleaned = cleaned.split("?", 1)[0].split("&", 1)[0].split("#", 1)[0]
    cleaned = cleaned.strip("/").rstrip(".,;")
    return cleaned if _YOUTUBE_ID_RE.fullmatch(cleaned) else None


def default_output_path(source: str) -> Path:
    if is_url(source):
        return Path.cwd() / "transcript.txt"
    path = Path(source).expanduser()
    return path.with_name("transcript.txt")


def require_executable(name: str) -> str:
    venv_executable = Path(sys.executable).resolve().parent / name
    if venv_executable.exists():
        return str(venv_executable)
    executable = shutil.which(name)
    if not executable:
        raise TranscriptionError(f"Missing required executable: {name}")
    return executable


def summarize_downloader_error(detail: str) -> str:
    compact = " ".join(detail.split())
    lowered = compact.lower()
    if "sign in to confirm" in lowered or "not a bot" in lowered:
        return (
            "YouTube blocked this request with an anti-bot/sign-in challenge. "
            "Try a direct downloadable media URL or a local file. Browser cookies are not used by default."
        )
    if "precondition check failed" in lowered or "http error 400" in lowered:
        return (
            "YouTube rejected the downloader request with HTTP 400 / precondition-check failure. "
            "The app tried the current YouTube extractor fallback; update yt-dlp or try another URL."
        )
    if "http error 403" in lowered or "forbidden" in lowered:
        return (
            "YouTube blocked the media download with HTTP 403. "
            "Try again later, update yt-dlp, or use a direct downloadable media URL/local file."
        )
    if len(compact) > 700:
        return compact[:700].rstrip() + "..."
    return compact


def run_command(args: list[str]) -> None:
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        raise TranscriptionError(summarize_downloader_error(detail))


def convert_to_wav(input_path: Path, output_path: Path, sample_rate: int) -> None:
    if not input_path.exists():
        raise TranscriptionError(f"Input file not found: {input_path}")
    ffmpeg = require_executable("ffmpeg")
    run_command(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(input_path),
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            str(output_path),
        ]
    )


def download_url_to_media(url: str, temp_dir: Path) -> Path:
    download_url = canonical_watch_url(url) if is_youtube_url(url) else url
    if not download_url:
        raise TranscriptionError("Could not determine YouTube video id.")

    base_options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "retries": 2,
        "fragment_retries": 2,
        "noprogress": True,
        "logger": _SilentYtdlpLogger(),
        "format": "bestaudio[acodec!=none]/bestaudio/best",
        "outtmpl": str(temp_dir / "download.%(ext)s"),
    }
    attempts: list[dict[str, Any]] = []
    if is_youtube_url(download_url):
        attempts.append({**base_options, "extractor_args": {"youtube": {"player_client": ["mweb"]}}})
        attempts.append(
            {**base_options, "extractor_args": {"youtube": {"player_client": ["default", "-android_sdkless"]}}}
        )
    attempts.append(base_options)

    errors: list[str] = []
    for options in attempts:
        try:
            return _download_with_ytdlp(download_url, temp_dir, options)
        except TranscriptionError as exc:
            errors.append(str(exc))
    raise TranscriptionError(errors[-1] if errors else "yt-dlp failed to download the URL")


def _download_with_ytdlp(url: str, temp_dir: Path, options: dict[str, Any]) -> Path:
    try:
        import yt_dlp  # type: ignore[import]
    except Exception as exc:  # noqa: BLE001
        raise TranscriptionError("Missing required Python package: yt-dlp") from exc

    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            downloader.download([url])
    except Exception as exc:  # noqa: BLE001
        raise TranscriptionError(summarize_downloader_error(str(exc))) from exc

    downloaded = sorted(
        path
        for path in temp_dir.iterdir()
        if path.is_file()
        and path.name.startswith("download.")
        and not path.name.endswith((".part", ".ytdl", ".json", ".description"))
    )
    if not downloaded:
        raise TranscriptionError("yt-dlp did not produce an audio file")
    return downloaded[0]


def download_url_to_wav(url: str, output_path: Path, sample_rate: int, temp_dir: Path) -> None:
    media_path = download_url_to_media(url, temp_dir)
    convert_to_wav(media_path, output_path, sample_rate)


def load_asr_model() -> Any:
    return onnx_asr.load_model(
        "nemo-parakeet-tdt-0.6b-v2",
        path=MODEL_DIR,
        quantization="int8",
        providers=["CPUExecutionProvider"],
    )


def transcribe_source(
    source: str,
    *,
    output_path: Path | None = None,
    config: dict[str, Any],
    cleanup_enabled: bool | None = None,
) -> TranscriptionResult:
    sample_rate = int(config.get("sample_rate", 16000))
    destination = Path(output_path).expanduser() if output_path else default_output_path(source)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="macos-local-asr-file-") as tmp:
        temp_dir = Path(tmp)
        wav_path = temp_dir / "input.wav"
        if is_url(source):
            download_url_to_wav(source, wav_path, sample_rate, temp_dir)
        else:
            convert_to_wav(Path(source).expanduser(), wav_path, sample_rate)

        model = load_asr_model()
        started = time.perf_counter()
        raw_text = str(model.recognize(wav_path, sample_rate=sample_rate)).strip()
        asr_latency = time.perf_counter() - started

    runtime_config = dict(config)
    if cleanup_enabled is not None:
        runtime_config["cleanup_enabled"] = cleanup_enabled

    text = raw_text
    cleanup_latency = 0.0
    if raw_text and runtime_config.get("cleanup_enabled", False):
        cleanup_started = time.perf_counter()
        try:
            text = cleanup_text(raw_text, runtime_config)
        except CleanupError:
            text = raw_text
        cleanup_latency = time.perf_counter() - cleanup_started

    destination.write_text(text + ("\n" if text else ""), encoding="utf-8")
    return TranscriptionResult(
        source=source,
        output_path=destination,
        text=text,
        raw_text=raw_text,
        audio_sec=None,
        asr_latency_sec=asr_latency,
        cleanup_latency_sec=cleanup_latency,
    )
