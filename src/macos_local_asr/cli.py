from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .configuration import (
    APP_DIR,
    CONFIG_PATH,
    HISTORY_PATH,
    LOG_PATH,
    MODEL_DIR,
    MODEL_FILES,
    coerce_config_value,
    hotkey_label,
    load_config,
    parse_hotkey,
    save_config,
    set_config_value,
    validate_config,
)


LABEL = os.environ.get("MACOS_LOCAL_ASR_LABEL", "com.pankajrajdeo.macos-local-asr")
PLIST_PATH = Path(
    os.environ.get(
        "MACOS_LOCAL_ASR_PLIST",
        str(Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"),
    )
)


def print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False))


def cmd_config(args: argparse.Namespace) -> int:
    if args.config_action == "show":
        print_json(load_config())
        return 0
    if args.config_action == "get":
        config = load_config()
        if args.key not in config:
            print(f"Unknown config key: {args.key}", file=sys.stderr)
            return 2
        value = config[args.key]
        if isinstance(value, (dict, list, bool, int, float)):
            print_json(value)
        else:
            print(value)
        return 0
    if args.config_action == "set":
        try:
            config = set_config_value(args.key, args.value)
        except (KeyError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(f"{args.key}={config[args.key]}")
        return 0
    if args.config_action == "validate":
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
        except Exception as exc:  # noqa: BLE001
            print(f"Config unreadable: {exc}", file=sys.stderr)
            return 1
        errors = validate_config(raw)
        if errors:
            for error in errors:
                print(f"error: {error}", file=sys.stderr)
            return 1
        print(f"Config OK: {CONFIG_PATH}")
        return 0
    raise AssertionError(args.config_action)


def cmd_hotkey(args: argparse.Namespace) -> int:
    if args.hotkey_action != "set":
        raise AssertionError(args.hotkey_action)
    key = {"push": "hotkey", "push-to-talk": "hotkey", "lock": "lock_hotkey", "locked": "lock_hotkey"}[args.mode]
    try:
        value = coerce_config_value(key, args.value)
        config = load_config()
        config[key] = value
        errors = validate_config(config)
        if errors:
            raise ValueError("; ".join(errors))
        save_config(config)
    except (KeyError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"{key}={value} ({hotkey_label(parse_hotkey(str(value)))})")
    print("Restart the service for this change to take effect.")
    return 0


def iter_history(path: Path = HISTORY_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def cmd_history(args: argparse.Namespace) -> int:
    rows = iter_history()
    if args.history_action == "search":
        query = args.query.lower().strip()
        matches = [row for row in rows if query in str(row.get("text", "")).lower()]
        matches = matches[-args.limit :]
        for row in reversed(matches):
            created = row.get("created_at")
            when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created)) if isinstance(created, (int, float)) else "unknown"
            latency = row.get("latency_sec")
            latency_text = f"{latency:.2f}s" if isinstance(latency, (int, float)) else "n/a"
            print(f"[{when}] latency={latency_text}")
            print(str(row.get("text", "")).strip())
            print()
        print(f"{len(matches)} match(es)")
        return 0
    if args.history_action == "stats":
        total_words = sum(len(str(row.get("text", "")).split()) for row in rows)
        total_chars = sum(len(str(row.get("text", ""))) for row in rows)
        print_json({"entries": len(rows), "words": total_words, "characters": total_chars, "path": str(HISTORY_PATH)})
        return 0
    raise AssertionError(args.history_action)


def launchctl_state() -> tuple[str, str]:
    domain = f"gui/{os.getuid()}/{LABEL}"
    result = subprocess.run(["launchctl", "print", domain], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return "not_loaded", result.stderr.strip() or result.stdout.strip()
    state = "unknown"
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("state ="):
            state = stripped.split("=", 1)[1].strip()
            break
    return state, result.stdout


def accessibility_trusted() -> bool | None:
    try:
        from ApplicationServices import AXIsProcessTrusted  # type: ignore
    except Exception:  # noqa: BLE001
        return None
    return bool(AXIsProcessTrusted())


def model_health() -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for name in MODEL_FILES:
        path = MODEL_DIR / name
        ok = path.exists()
        detail = "present" if ok else "missing"
        if ok and name.endswith(".onnx"):
            head = path.read_bytes()[:80]
            if head.startswith(b"version https://git-lfs.github.com/spec"):
                ok = False
                detail = "git-lfs pointer, not model bytes"
        checks.append({"name": f"model:{name}", "ok": ok, "detail": detail, "path": str(path)})
    return checks


def recent_log_warnings() -> list[str]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]
    patterns = ("CGEventTap creation failed", "recording captured no samples", "fatal:", "audio status:")
    return [line for line in lines if any(pattern in line for pattern in patterns)][-10:]


def cmd_health(args: argparse.Namespace) -> int:
    config_errors = validate_config(json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {})
    launch_state, launch_detail = launchctl_state()
    ax = accessibility_trusted()

    checks: list[dict[str, Any]] = [
        {"name": "app_dir", "ok": APP_DIR.exists(), "detail": str(APP_DIR)},
        {"name": "config", "ok": not config_errors, "detail": "; ".join(config_errors) if config_errors else str(CONFIG_PATH)},
        {"name": "model_dir", "ok": MODEL_DIR.exists(), "detail": str(MODEL_DIR)},
        {"name": "launch_agent_plist", "ok": PLIST_PATH.exists(), "detail": str(PLIST_PATH)},
        {"name": "launch_agent_state", "ok": launch_state == "running", "detail": launch_state},
        {
            "name": "accessibility_permission",
            "ok": ax is True,
            "detail": "trusted" if ax is True else ("not trusted" if ax is False else "unavailable"),
        },
    ]
    checks.extend(model_health())
    warnings = recent_log_warnings()
    payload = {"checks": checks, "warnings": warnings}

    if args.json:
        print_json(payload)
    else:
        for check in checks:
            marker = "OK" if check["ok"] else "FAIL"
            print(f"{marker:4} {check['name']}: {check['detail']}")
        if warnings:
            print()
            print("Recent warnings:")
            for warning in warnings:
                print(f"- {warning}")
        print()
        print("Microphone and Input Monitoring are managed by macOS TCC. Run `macos-local-asr permissions` if recording or hotkeys fail.")

    return 0 if all(check["ok"] for check in checks if check["name"] != "accessibility_permission") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="macos-local-asr", description="Control and inspect macOS-localASR.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    config = subparsers.add_parser("config", help="Read, write, and validate config.")
    config_sub = config.add_subparsers(dest="config_action", required=True)
    config_sub.add_parser("show", help="Print full config JSON.")
    get = config_sub.add_parser("get", help="Print one config value.")
    get.add_argument("key")
    set_parser = config_sub.add_parser("set", help="Set one config value.")
    set_parser.add_argument("key")
    set_parser.add_argument("value")
    config_sub.add_parser("validate", help="Validate the config file.")
    config.set_defaults(func=cmd_config)

    hotkey = subparsers.add_parser("hotkey", help="Update hotkeys.")
    hotkey_sub = hotkey.add_subparsers(dest="hotkey_action", required=True)
    hotkey_set = hotkey_sub.add_parser("set", help="Set a hotkey.")
    hotkey_set.add_argument("mode", choices=["push", "push-to-talk", "lock", "locked"])
    hotkey_set.add_argument("value", help="Example: cmd+option")
    hotkey.set_defaults(func=cmd_hotkey)

    history = subparsers.add_parser("history", help="Search local transcript history.")
    history_sub = history.add_subparsers(dest="history_action", required=True)
    search = history_sub.add_parser("search", help="Search history text.")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=20)
    history_sub.add_parser("stats", help="Show local history statistics.")
    history.set_defaults(func=cmd_history)

    health = subparsers.add_parser("health", help="Check installed runtime health.")
    health.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    health.set_defaults(func=cmd_health)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

