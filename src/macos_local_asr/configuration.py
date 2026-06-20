from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


APP_DIR = Path(
    os.environ.get(
        "MACOS_LOCAL_ASR_APP_DIR",
        str(Path.home() / "Library" / "Application Support" / "macOS-localASR"),
    )
)
CONFIG_PATH = APP_DIR / "config.json"
MODEL_SUBDIR = "parakeet-tdt-0.6b-v2-onnx-int8"
MODEL_DIR = Path(os.environ.get("MACOS_LOCAL_ASR_MODEL_DIR", str(APP_DIR / "models" / MODEL_SUBDIR)))
HISTORY_PATH = APP_DIR / "history.jsonl"
LOG_DIR = APP_DIR / "logs"
LOG_PATH = LOG_DIR / "daemon.log"
CONTROL_SOCKET_PATH = APP_DIR / "control.sock"
KEY_ESC = 53

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

DEFAULT_CLEANUP_PROMPT = """Light cleanup style:
- Fix punctuation, capitalization, spacing, and obvious ASR slips.
- Preserve the speaker's wording and meaning.
- Keep the original language.
- Do not summarize or rewrite heavily."""

DEFAULT_CONFIG: dict[str, Any] = {
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
    "log_max_bytes": 1_048_576,
    "log_backup_count": 5,
    "cleanup_enabled": False,
    "cleanup_provider": "ollama",
    "cleanup_model": "",
    "cleanup_api_base": "http://127.0.0.1:11434",
    "cleanup_api_key": "",
    "cleanup_prompt": DEFAULT_CLEANUP_PROMPT,
}

CONFIG_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "macOS-localASR configuration",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "hotkey": {"type": "string", "minLength": 1},
        "lock_hotkey": {"type": "string", "minLength": 1},
        "sample_rate": {"type": "integer", "enum": [16000]},
        "paste_into_active_app": {"type": "boolean"},
        "copy_to_clipboard": {"type": "boolean"},
        "preserve_clipboard": {"type": "boolean"},
        "clipboard_restore_delay_seconds": {"type": "number", "minimum": 0, "maximum": 3},
        "min_recording_seconds": {"type": "number", "minimum": 0, "maximum": 30},
        "window_width": {"type": "integer", "minimum": 120, "maximum": 800},
        "window_height": {"type": "integer", "minimum": 28, "maximum": 240},
        "window_bottom_margin": {"type": "integer", "minimum": 0, "maximum": 800},
        "vad_enabled": {"type": "boolean"},
        "vad_aggressiveness": {"type": "integer", "minimum": 0, "maximum": 3},
        "vad_frame_ms": {"type": "integer", "enum": [10, 20, 30]},
        "vad_start_padding_ms": {"type": "integer", "minimum": 0, "maximum": 2000},
        "vad_end_padding_ms": {"type": "integer", "minimum": 0, "maximum": 3000},
        "vad_min_speech_ms": {"type": "integer", "minimum": 0, "maximum": 5000},
        "vad_audible_rms": {"type": "number", "minimum": 0, "maximum": 1},
        "log_max_bytes": {"type": "integer", "minimum": 65536, "maximum": 104857600},
        "log_backup_count": {"type": "integer", "minimum": 0, "maximum": 50},
        "cleanup_enabled": {"type": "boolean"},
        "cleanup_provider": {"type": "string", "enum": ["ollama", "openai_compatible"]},
        "cleanup_model": {"type": "string", "minLength": 0},
        "cleanup_api_base": {"type": "string", "minLength": 0},
        "cleanup_api_key": {"type": "string", "minLength": 0},
        "cleanup_prompt": {"type": "string", "minLength": 1},
    },
}

SUPPORTED_MODIFIERS = frozenset({"cmd", "option", "ctrl"})


def normalize_key(name: str) -> str:
    normalized = name.strip().lower()
    aliases = {
        "key.cmd": "cmd",
        "key.cmd_l": "cmd",
        "key.cmd_r": "cmd",
        "command": "cmd",
        "cmd": "cmd",
        "key.alt": "option",
        "key.alt_l": "option",
        "key.alt_r": "option",
        "alt": "option",
        "option": "option",
        "control": "ctrl",
        "ctrl": "ctrl",
        "key.ctrl": "ctrl",
        "key.ctrl_l": "ctrl",
        "key.ctrl_r": "ctrl",
    }
    return aliases.get(normalized, normalized)


def parse_hotkey(value: str) -> frozenset[str]:
    return frozenset(normalize_key(part) for part in value.split("+") if part.strip())


def hotkey_label(keys: set[str] | frozenset[str]) -> str:
    labels = {"cmd": "Command", "option": "Option", "ctrl": "Control"}
    ordered = [key for key in ("ctrl", "cmd", "option") if key in keys]
    ordered.extend(sorted(keys.difference(ordered)))
    return " + ".join(labels.get(key, key) for key in ordered)


def merge_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    if raw:
        config.update(raw)
    return config


def load_config(path: Path = CONFIG_PATH, *, create: bool = True) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        config = dict(DEFAULT_CONFIG)
        if create:
            save_config(config, path)
        return config
    return merge_config(json.loads(path.read_text(encoding="utf-8")))


def save_config(config: dict[str, Any], path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def coerce_config_value(key: str, raw_value: str) -> Any:
    if key not in DEFAULT_CONFIG:
        raise KeyError(f"Unknown config key: {key}")
    default = DEFAULT_CONFIG[key]
    if isinstance(default, bool):
        normalized = raw_value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        raise ValueError(f"{key} must be a boolean: true/false")
    if isinstance(default, int) and not isinstance(default, bool):
        return int(raw_value)
    if isinstance(default, float):
        return float(raw_value)
    return raw_value


def validate_hotkey(value: str, key_name: str) -> list[str]:
    keys = parse_hotkey(value)
    errors: list[str] = []
    if not keys:
        errors.append(f"{key_name} must include at least one key")
    unsupported = sorted(keys.difference(SUPPORTED_MODIFIERS))
    if unsupported:
        errors.append(f"{key_name} includes unsupported key(s): {', '.join(unsupported)}")
    return errors


def validate_config(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    unknown = sorted(set(config).difference(DEFAULT_CONFIG))
    if unknown:
        errors.append(f"Unknown config key(s): {', '.join(unknown)}")

    merged = merge_config({key: value for key, value in config.items() if key in DEFAULT_CONFIG})
    properties = CONFIG_SCHEMA["properties"]
    for key, default in DEFAULT_CONFIG.items():
        value = merged.get(key)
        schema = properties[key]
        expected_type = schema["type"]
        if expected_type == "boolean":
            if not isinstance(value, bool):
                errors.append(f"{key} must be boolean")
        elif expected_type == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                errors.append(f"{key} must be integer")
                continue
            if "enum" in schema and value not in schema["enum"]:
                errors.append(f"{key} must be one of {schema['enum']}")
            if "minimum" in schema and value < schema["minimum"]:
                errors.append(f"{key} must be >= {schema['minimum']}")
            if "maximum" in schema and value > schema["maximum"]:
                errors.append(f"{key} must be <= {schema['maximum']}")
        elif expected_type == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(f"{key} must be number")
                continue
            if "minimum" in schema and value < schema["minimum"]:
                errors.append(f"{key} must be >= {schema['minimum']}")
            if "maximum" in schema and value > schema["maximum"]:
                errors.append(f"{key} must be <= {schema['maximum']}")
        elif expected_type == "string":
            if not isinstance(value, str):
                errors.append(f"{key} must be string")
                continue
            if "enum" in schema and value not in schema["enum"]:
                errors.append(f"{key} must be one of {schema['enum']}")
            if schema.get("minLength", 0) > 0 and not value.strip():
                errors.append(f"{key} must be non-empty string")

    errors.extend(validate_hotkey(str(merged["hotkey"]), "hotkey"))
    errors.extend(validate_hotkey(str(merged["lock_hotkey"]), "lock_hotkey"))
    if merged.get("cleanup_enabled"):
        if not str(merged.get("cleanup_model", "")).strip():
            errors.append("cleanup_model must be set when cleanup_enabled is true")
        if not str(merged.get("cleanup_prompt", "")).strip():
            errors.append("cleanup_prompt must be set when cleanup_enabled is true")
        if str(merged.get("cleanup_provider")) == "openai_compatible" and not str(merged.get("cleanup_api_base", "")).strip():
            errors.append("cleanup_api_base must be set for openai_compatible cleanup")
    return errors


def set_config_value(key: str, raw_value: str, path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = load_config(path)
    config[key] = coerce_config_value(key, raw_value)
    errors = validate_config(config)
    if errors:
        raise ValueError("; ".join(errors))
    save_config(config, path)
    return config


def load_log_rotation_settings() -> tuple[int, int]:
    try:
        config = load_config(create=False)
    except Exception:  # noqa: BLE001
        config = DEFAULT_CONFIG
    return int(config.get("log_max_bytes", DEFAULT_CONFIG["log_max_bytes"])), int(
        config.get("log_backup_count", DEFAULT_CONFIG["log_backup_count"])
    )
