from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


APP_DIR = Path.home() / "Library" / "Application Support" / "macOS-localASR"
LABEL = "com.pankajrajdeo.macos-local-asr"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
BIN_PATH = Path.home() / "bin" / "macos-local-asr"


def run(args: list[str], *, check: bool = False) -> None:
    print("+", " ".join(args))
    subprocess.run(args, check=check, text=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Uninstall macOS-localASR.")
    parser.add_argument("--keep-data", action="store_true", help="Keep app support data, model, logs, and history.")
    args = parser.parse_args()

    uid = str(os.getuid())
    run(["launchctl", "bootout", f"gui/{uid}", str(PLIST_PATH)])
    if PLIST_PATH.exists():
        PLIST_PATH.unlink()
        print(f"Removed {PLIST_PATH}")
    if BIN_PATH.exists():
        BIN_PATH.unlink()
        print(f"Removed {BIN_PATH}")
    if not args.keep_data and APP_DIR.exists():
        shutil.rmtree(APP_DIR)
        print(f"Removed {APP_DIR}")
    elif args.keep_data:
        print(f"Kept {APP_DIR}")


if __name__ == "__main__":
    main()
