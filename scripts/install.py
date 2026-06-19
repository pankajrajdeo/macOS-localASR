from __future__ import annotations

import argparse
import json
import os
import plistlib
import shutil
import stat
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DAEMON = REPO_ROOT / "src" / "macos_local_asr" / "daemon.py"
SOURCE_README = REPO_ROOT / "README.md"
SOURCE_NOTICE = REPO_ROOT / "NOTICE.md"
SOURCE_REQUIREMENTS = REPO_ROOT / "requirements.txt"
SOURCE_MODEL_DIR = REPO_ROOT / "models" / "parakeet-tdt-0.6b-v2-onnx-int8"
REQUIREMENTS = REPO_ROOT / "requirements.txt"

APP_DIR = Path.home() / "Library" / "Application Support" / "macOS-localASR"
MODEL_DIR = APP_DIR / "models" / "parakeet-tdt-0.6b-v2-onnx-int8"
VENV_DIR = APP_DIR / ".venv"
LOG_DIR = APP_DIR / "logs"
LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
LABEL = "com.pankajrajdeo.macos-local-asr"
PLIST_PATH = LAUNCH_AGENTS_DIR / f"{LABEL}.plist"
BIN_DIR = Path.home() / "bin"
BIN_PATH = BIN_DIR / "macos-local-asr"

MODEL_FILES = [
    "config.json",
    "vocab.txt",
    "nemo128.onnx",
    "nemo80.onnx",
    "encoder-model.int8.onnx",
    "decoder_joint-model.int8.onnx",
    "README.md",
    "ATTRIBUTION.md",
]

DEFAULT_CONFIG = {
    "hotkey": "cmd+option",
    "lock_hotkey": "ctrl+cmd+option",
    "sample_rate": 16000,
    "paste_into_active_app": True,
    "copy_to_clipboard": False,
    "preserve_clipboard": True,
    "clipboard_restore_delay_seconds": 0.35,
    "min_recording_seconds": 0.25,
    "window_width": 230,
    "window_height": 44,
    "window_bottom_margin": 94,
    "vad_enabled": True,
    "vad_aggressiveness": 2,
    "vad_frame_ms": 20,
    "vad_start_padding_ms": 160,
    "vad_end_padding_ms": 320,
    "vad_min_speech_ms": 80,
    "vad_audible_rms": 0.0025,
}


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(args))
    return subprocess.run(args, check=check, text=True)


def ensure_model_present() -> None:
    missing = [name for name in MODEL_FILES if not (SOURCE_MODEL_DIR / name).exists()]
    if missing:
        raise SystemExit(
            "Missing bundled model files. If you cloned the repo, run `git lfs pull` first.\n"
            f"Missing: {', '.join(missing)}"
        )
    pointer = (SOURCE_MODEL_DIR / "encoder-model.int8.onnx").read_bytes()[:80]
    if pointer.startswith(b"version https://git-lfs.github.com/spec"):
        raise SystemExit("Git LFS pointer found instead of model bytes. Run `git lfs pull` and retry.")


def copy_model() -> None:
    ensure_model_present()
    if MODEL_DIR.exists():
        shutil.rmtree(MODEL_DIR)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for name in MODEL_FILES:
        shutil.copy2(SOURCE_MODEL_DIR / name, MODEL_DIR / name)
    provenance = SOURCE_MODEL_DIR / "provenance"
    if provenance.exists():
        shutil.copytree(provenance, MODEL_DIR / "provenance")


def create_venv() -> None:
    if not (VENV_DIR / "bin" / "python").exists():
        run([sys.executable, "-m", "venv", str(VENV_DIR)])
    python = VENV_DIR / "bin" / "python"
    run([str(python), "-m", "pip", "install", "-U", "pip"])
    run([str(python), "-m", "pip", "install", "-r", str(REQUIREMENTS)])


def install_runtime_files() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_DAEMON, APP_DIR / "dictation_daemon.py")
    shutil.copy2(SOURCE_README, APP_DIR / "README.md")
    shutil.copy2(SOURCE_NOTICE, APP_DIR / "NOTICE.md")
    shutil.copy2(SOURCE_REQUIREMENTS, APP_DIR / "requirements.txt")
    config_path = APP_DIR / "config.json"
    if not config_path.exists():
        config_path.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n", encoding="utf-8")
    else:
        existing = json.loads(config_path.read_text(encoding="utf-8"))
        config = dict(DEFAULT_CONFIG)
        config.update(existing)
        if "preserve_clipboard" not in existing and config.get("paste_into_active_app", True):
            config["copy_to_clipboard"] = False
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def install_command() -> None:
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    BIN_PATH.write_text(
        f"""#!/bin/zsh
LABEL="{LABEL}"
PLIST="{PLIST_PATH}"
PYTHON="{VENV_DIR}/bin/python"
DAEMON="{APP_DIR}/dictation_daemon.py"
LOG_DIR="{LOG_DIR}"
DOMAIN="gui/$(id -u)"

case "${{1:-start}}" in
  start)
    if ! launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
      launchctl bootstrap "$DOMAIN" "$PLIST"
      launchctl kickstart "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
    fi
    launchctl print "$DOMAIN/$LABEL" | sed -n '1,55p'
    ;;
  stop)
    launchctl bootout "$DOMAIN" "$PLIST" 2>/dev/null || true
    ;;
  restart)
    launchctl bootout "$DOMAIN" "$PLIST" 2>/dev/null || true
    launchctl bootstrap "$DOMAIN" "$PLIST"
    launchctl kickstart -k "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
    launchctl print "$DOMAIN/$LABEL" | sed -n '1,55p'
    ;;
  status)
    launchctl print "$DOMAIN/$LABEL"
    ;;
  logs)
    tail -f "$LOG_DIR/daemon.log" "$LOG_DIR/launchd.err.log" "$LOG_DIR/launchd.out.log"
    ;;
  permissions)
    open -R "$PYTHON"
    open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
    open "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
    open "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
    ;;
  run)
    MACOS_LOCAL_ASR_APP_DIR="{APP_DIR}" exec "$PYTHON" "$DAEMON"
    ;;
  test-ui)
    MACOS_LOCAL_ASR_APP_DIR="{APP_DIR}" exec "$PYTHON" "$DAEMON" --test-ui
    ;;
  uninstall)
    launchctl bootout "$DOMAIN" "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    rm -rf "{APP_DIR}"
    rm -f "$0"
    echo "Removed macOS-localASR."
    ;;
  *)
    echo "Usage: macos-local-asr [start|stop|restart|status|logs|permissions|run|test-ui|uninstall]"
    exit 2
    ;;
esac
""",
        encoding="utf-8",
    )
    BIN_PATH.chmod(BIN_PATH.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def install_launch_agent() -> None:
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": LABEL,
        "ProgramArguments": [str(VENV_DIR / "bin" / "python"), str(APP_DIR / "dictation_daemon.py")],
        "RunAtLoad": True,
        "KeepAlive": False,
        "StandardOutPath": str(LOG_DIR / "launchd.out.log"),
        "StandardErrorPath": str(LOG_DIR / "launchd.err.log"),
        "WorkingDirectory": str(APP_DIR),
        "EnvironmentVariables": {
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "MACOS_LOCAL_ASR_APP_DIR": str(APP_DIR),
        },
    }
    with PLIST_PATH.open("wb") as handle:
        plistlib.dump(plist, handle)


def load_model_smoke() -> None:
    python = VENV_DIR / "bin" / "python"
    code = (
        "from pathlib import Path; import onnx_asr; "
        f"m=onnx_asr.load_model('nemo-parakeet-tdt-0.6b-v2', path=Path(r'{MODEL_DIR}'), "
        "quantization='int8', providers=['CPUExecutionProvider']); "
        "print('model smoke ok')"
    )
    run([str(python), "-c", code])


def start_launch_agent() -> None:
    uid = str(os.getuid())
    run(["launchctl", "bootout", f"gui/{uid}", str(PLIST_PATH)], check=False)
    run(["launchctl", "bootstrap", f"gui/{uid}", str(PLIST_PATH)])
    run(["launchctl", "kickstart", "-k", f"gui/{uid}/{LABEL}"], check=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Install macOS-localASR as a user LaunchAgent.")
    parser.add_argument("--no-start", action="store_true", help="Install files but do not start the LaunchAgent.")
    args = parser.parse_args()

    install_runtime_files()
    copy_model()
    create_venv()
    install_command()
    install_launch_agent()
    load_model_smoke()
    if not args.no_start:
        start_launch_agent()

    print()
    print(f"Installed app dir: {APP_DIR}")
    print(f"Command: {BIN_PATH}")
    print(f"LaunchAgent: {PLIST_PATH}")
    print("Default push-to-talk hotkey: hold Command + Option")
    print("Default lock-mode hotkey: press Control + Command + Option, then press Escape to transcribe")
    print("Run `macos-local-asr permissions` and grant Microphone, Accessibility, and Input Monitoring.")


if __name__ == "__main__":
    main()
