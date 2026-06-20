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
SOURCE_ROOT = REPO_ROOT / "src"
SOURCE_PACKAGE_DIR = SOURCE_ROOT / "macos_local_asr"
SOURCE_README = REPO_ROOT / "README.md"
SOURCE_NOTICE = REPO_ROOT / "NOTICE.md"
SOURCE_REQUIREMENTS = REPO_ROOT / "requirements.txt"
SOURCE_MODEL_DIR = REPO_ROOT / "models" / "parakeet-tdt-0.6b-v2-onnx-int8"
REQUIREMENTS = REPO_ROOT / "requirements.txt"
sys.path.insert(0, str(SOURCE_ROOT))

from macos_local_asr.configuration import DEFAULT_CONFIG, MODEL_FILES  # noqa: E402

APP_DIR = Path.home() / "Library" / "Application Support" / "macOS-localASR"
MODEL_DIR = APP_DIR / "models" / "parakeet-tdt-0.6b-v2-onnx-int8"
VENV_DIR = APP_DIR / ".venv"
LOG_DIR = APP_DIR / "logs"
RUNTIME_PACKAGE_DIR = APP_DIR / "macos_local_asr"
LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
LABEL = "com.pankajrajdeo.macos-local-asr"
PLIST_PATH = LAUNCH_AGENTS_DIR / f"{LABEL}.plist"
BIN_DIR = Path.home() / "bin"
BIN_PATH = BIN_DIR / "macos-local-asr"

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
    if RUNTIME_PACKAGE_DIR.exists():
        shutil.rmtree(RUNTIME_PACKAGE_DIR)
    shutil.copytree(
        SOURCE_PACKAGE_DIR,
        RUNTIME_PACKAGE_DIR,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
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
APP_DIR="{APP_DIR}"
LOG_DIR="{LOG_DIR}"
DOMAIN="gui/$(id -u)"
export MACOS_LOCAL_ASR_APP_DIR="$APP_DIR"
export MACOS_LOCAL_ASR_LABEL="$LABEL"
export MACOS_LOCAL_ASR_PLIST="$PLIST"
export PYTHONPATH="$APP_DIR"

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
    exec "$PYTHON" -m macos_local_asr.daemon
    ;;
  test-ui)
    exec "$PYTHON" -m macos_local_asr.daemon --test-ui
    ;;
  config|hotkey|history|health|control|cleanup|transcribe)
    exec "$PYTHON" -m macos_local_asr.cli "$@"
    ;;
  uninstall)
    launchctl bootout "$DOMAIN" "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    rm -rf "$APP_DIR"
    rm -f "$0"
    echo "Removed macOS-localASR."
    ;;
  *)
    echo "Usage: macos-local-asr [start|stop|restart|status|logs|permissions|run|test-ui|config|hotkey|history|health|control|cleanup|transcribe|uninstall]"
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
        "ProgramArguments": [str(VENV_DIR / "bin" / "python"), "-m", "macos_local_asr.daemon"],
        "RunAtLoad": True,
        "KeepAlive": False,
        "StandardOutPath": str(LOG_DIR / "launchd.out.log"),
        "StandardErrorPath": str(LOG_DIR / "launchd.err.log"),
        "WorkingDirectory": str(APP_DIR),
        "EnvironmentVariables": {
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "MACOS_LOCAL_ASR_APP_DIR": str(APP_DIR),
            "MACOS_LOCAL_ASR_LABEL": LABEL,
            "MACOS_LOCAL_ASR_PLIST": str(PLIST_PATH),
            "PYTHONPATH": str(APP_DIR),
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
