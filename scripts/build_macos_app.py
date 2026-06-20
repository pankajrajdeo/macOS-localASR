from __future__ import annotations

import argparse
import plistlib
import shutil
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = REPO_ROOT / "apps" / "macos" / "LocalASRMenuBar"
DIST_DIR = REPO_ROOT / "dist"
APP_NAME = "LocalASR"
APP_BUNDLE = DIST_DIR / f"{APP_NAME}.app"
BUNDLE_ID = "com.pankajrajdeo.LocalASR"


def run(args: list[str]) -> None:
    print("+", " ".join(args))
    subprocess.run(args, check=True, text=True)


def find_executable(configuration: str) -> Path:
    candidates = [
        PACKAGE_DIR / ".build" / configuration / "LocalASRMenuBar",
        *PACKAGE_DIR.glob(f".build/*-apple-macosx/{configuration}/LocalASRMenuBar"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise SystemExit(f"Swift build succeeded but executable was not found under {PACKAGE_DIR / '.build'}")


def write_info_plist(path: Path) -> None:
    payload = {
        "CFBundleDevelopmentRegion": "en",
        "CFBundleDisplayName": APP_NAME,
        "CFBundleExecutable": APP_NAME,
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": APP_NAME,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "0.2.0",
        "CFBundleVersion": "2",
        "LSMinimumSystemVersion": "14.0",
        "LSUIElement": True,
        "NSAppleEventsUsageDescription": "LocalASR needs automation access to paste transcripts into the active app.",
        "NSMicrophoneUsageDescription": "LocalASR records your microphone locally for dictation.",
        "NSHumanReadableCopyright": "Copyright © 2026 macOS-localASR contributors.",
        "NSSupportsAutomaticTermination": False,
        "NSSupportsSuddenTermination": False,
    }
    with path.open("wb") as handle:
        plistlib.dump(payload, handle)


def build_app(*, release: bool, ad_hoc_sign: bool) -> None:
    configuration = "release" if release else "debug"
    build_args = ["swift", "build", "--package-path", str(PACKAGE_DIR)]
    if release:
        build_args.insert(2, "-c")
        build_args.insert(3, "release")
    run(build_args)

    executable = find_executable(configuration)
    if APP_BUNDLE.exists():
        shutil.rmtree(APP_BUNDLE)

    contents = APP_BUNDLE / "Contents"
    macos_dir = contents / "MacOS"
    resources_dir = contents / "Resources"
    macos_dir.mkdir(parents=True)
    resources_dir.mkdir(parents=True)

    app_executable = macos_dir / APP_NAME
    shutil.copy2(executable, app_executable)
    app_executable.chmod(app_executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    write_info_plist(contents / "Info.plist")

    readme = PACKAGE_DIR / "README.md"
    if readme.exists():
        shutil.copy2(readme, resources_dir / "README.md")

    if ad_hoc_sign:
        run(["codesign", "--force", "--deep", "--sign", "-", str(APP_BUNDLE)])

    print(f"Built {APP_BUNDLE}")
    print(f"Run it with: open {APP_BUNDLE}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the LocalASR macOS app bundle.")
    parser.add_argument("--debug", action="store_true", help="Build a debug app bundle instead of release.")
    parser.add_argument("--ad-hoc-sign", action="store_true", help="Ad-hoc sign the app bundle with codesign.")
    args = parser.parse_args()
    build_app(release=not args.debug, ad_hoc_sign=args.ad_hoc_sign)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
