from __future__ import annotations

import json
import queue
import socket
import subprocess
import sys
import tempfile
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import onnx_asr
import sounddevice as sd
import webrtcvad
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSEvent,
    NSMakePoint,
    NSMakeRect,
    NSPanel,
    NSPasteboard,
    NSPasteboardItem,
    NSPasteboardTypeString,
    NSScreen,
    NSScreenSaverWindowLevel,
    NSTimer,
    NSView,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorIgnoresCycle,
    NSWindowCollectionBehaviorStationary,
    NSWindowCollectionBehaviorTransient,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
    NSWorkspace,
)
from Quartz import (
    CFMachPortCreateRunLoopSource,
    CFRunLoopAddSource,
    CFRunLoopGetCurrent,
    CFRunLoopRun,
    CGEventGetFlags,
    CGEventGetIntegerValueField,
    CGEventMaskBit,
    CGEventTapCreate,
    CGEventTapEnable,
    kCFRunLoopCommonModes,
    kCGEventFlagMaskAlternate,
    kCGEventFlagMaskCommand,
    kCGEventFlagMaskControl,
    kCGEventFlagsChanged,
    kCGEventKeyDown,
    kCGEventTapDisabledByTimeout,
    kCGEventTapDisabledByUserInput,
    kCGEventTapOptionDefault,
    kCGHeadInsertEventTap,
    kCGKeyboardEventKeycode,
    kCGSessionEventTap,
)
from Foundation import NSData

try:
    from .cleanup import CleanupError, cleanup_text
    from .configuration import (
        APP_DIR,
        CONTROL_SOCKET_PATH,
        HISTORY_PATH,
        KEY_ESC,
        LOG_PATH,
        MODEL_DIR,
        hotkey_label,
        load_config,
        load_log_rotation_settings,
        parse_hotkey,
    )
except ImportError:  # pragma: no cover - direct script fallback for local debugging
    from cleanup import CleanupError, cleanup_text  # type: ignore
    from configuration import (  # type: ignore
        APP_DIR,
        CONTROL_SOCKET_PATH,
        HISTORY_PATH,
        KEY_ESC,
        LOG_PATH,
        MODEL_DIR,
        hotkey_label,
        load_config,
        load_log_rotation_settings,
        parse_hotkey,
    )


@dataclass
class Recording:
    frames: list[np.ndarray]
    started_at: float
    sample_rate: int


@dataclass
class VadStats:
    enabled: bool
    original_sec: float
    trimmed_sec: float
    speech_ms: float
    start_ms: float
    end_ms: float
    speech_frames: int
    total_frames: int
    reason: str


def log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rotate_log_if_needed(LOG_PATH)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"[{stamp}] {message}\n")


def rotate_log_if_needed(path: Path) -> None:
    max_bytes, backup_count = load_log_rotation_settings()
    if backup_count <= 0 or max_bytes <= 0 or not path.exists() or path.stat().st_size < max_bytes:
        return
    oldest = path.with_name(f"{path.name}.{backup_count}")
    if oldest.exists():
        oldest.unlink()
    for index in range(backup_count - 1, 0, -1):
        src = path.with_name(f"{path.name}.{index}")
        dst = path.with_name(f"{path.name}.{index + 1}")
        if src.exists():
            src.replace(dst)
    path.replace(path.with_name(f"{path.name}.1"))


def write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    clipped = np.clip(audio, -1.0, 1.0)
    pcm = (clipped * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())


def audio_to_pcm16(audio: np.ndarray) -> np.ndarray:
    clipped = np.clip(audio, -1.0, 1.0)
    return (clipped * 32767).astype("<i2")


def trim_audio_with_vad(audio: np.ndarray, sample_rate: int, config: dict[str, Any]) -> tuple[np.ndarray | None, VadStats]:
    original_sec = audio.size / float(sample_rate) if sample_rate else 0.0
    if not config.get("vad_enabled", True):
        return audio, VadStats(False, original_sec, original_sec, 0.0, 0.0, original_sec * 1000, 0, 0, "disabled")

    frame_ms = int(config.get("vad_frame_ms", 20))
    if frame_ms not in (10, 20, 30):
        frame_ms = 20
    frame_samples = int(sample_rate * frame_ms / 1000)
    if frame_samples <= 0 or audio.size < frame_samples:
        return audio, VadStats(True, original_sec, original_sec, original_sec * 1000, 0.0, original_sec * 1000, 0, 0, "too_short")

    pcm = audio_to_pcm16(audio)
    remainder = pcm.size % frame_samples
    if remainder:
        pcm = np.pad(pcm, (0, frame_samples - remainder), mode="constant")

    vad = webrtcvad.Vad(max(0, min(3, int(config.get("vad_aggressiveness", 2)))))
    speech_indices: list[int] = []
    total_frames = pcm.size // frame_samples
    for idx in range(total_frames):
        frame = pcm[idx * frame_samples : (idx + 1) * frame_samples]
        if vad.is_speech(frame.tobytes(), sample_rate):
            speech_indices.append(idx)

    rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
    audible_rms = float(config.get("vad_audible_rms", 0.0035))
    speech_ms = len(speech_indices) * frame_ms
    min_speech_ms = float(config.get("vad_min_speech_ms", 80))

    if rms < audible_rms:
        return None, VadStats(True, original_sec, 0.0, speech_ms, 0.0, 0.0, len(speech_indices), total_frames, "below_rms_floor")

    if not speech_indices:
        if rms >= audible_rms:
            return audio, VadStats(True, original_sec, original_sec, 0.0, 0.0, original_sec * 1000, 0, total_frames, "audible_fallback")
        return None, VadStats(True, original_sec, 0.0, 0.0, 0.0, 0.0, 0, total_frames, "no_speech")

    if speech_ms < min_speech_ms and rms < audible_rms:
        return None, VadStats(True, original_sec, 0.0, speech_ms, 0.0, 0.0, len(speech_indices), total_frames, "too_little_speech")

    start_padding = int(sample_rate * float(config.get("vad_start_padding_ms", 160)) / 1000)
    end_padding = int(sample_rate * float(config.get("vad_end_padding_ms", 320)) / 1000)
    start_sample = max(0, speech_indices[0] * frame_samples - start_padding)
    end_sample = min(audio.size, (speech_indices[-1] + 1) * frame_samples + end_padding)
    trimmed = audio[start_sample:end_sample]
    trimmed_sec = trimmed.size / float(sample_rate) if sample_rate else 0.0
    return trimmed, VadStats(
        True,
        original_sec,
        trimmed_sec,
        speech_ms,
        start_sample * 1000.0 / sample_rate,
        end_sample * 1000.0 / sample_rate,
        len(speech_indices),
        total_frames,
        "trimmed",
    )


ClipboardSnapshot = list[list[tuple[str, bytes]]]


def capture_clipboard() -> ClipboardSnapshot | None:
    try:
        snapshot: ClipboardSnapshot = []
        for item in NSPasteboard.generalPasteboard().pasteboardItems() or []:
            item_data: list[tuple[str, bytes]] = []
            for data_type in item.types() or []:
                data = item.dataForType_(data_type)
                if data is not None:
                    item_data.append((str(data_type), bytes(data)))
            if item_data:
                snapshot.append(item_data)
        return snapshot
    except Exception as exc:  # noqa: BLE001
        log(f"clipboard capture failed: {exc}")
        return None


def restore_clipboard(snapshot: ClipboardSnapshot | None) -> None:
    if snapshot is None:
        return
    try:
        pasteboard = NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        if not snapshot:
            return
        restored_items = []
        for item_data in snapshot:
            item = NSPasteboardItem.alloc().init()
            for data_type, payload in item_data:
                item.setData_forType_(NSData.dataWithBytes_length_(payload, len(payload)), data_type)
            restored_items.append(item)
        pasteboard.writeObjects_(restored_items)
    except Exception as exc:  # noqa: BLE001
        log(f"clipboard restore failed: {exc}")


def set_clipboard(text: str) -> None:
    pasteboard = NSPasteboard.generalPasteboard()
    pasteboard.clearContents()
    pasteboard.setString_forType_(text, NSPasteboardTypeString)


def paste_clipboard(target_bundle_id: str | None = None) -> None:
    if target_bundle_id:
        script = (
            f'tell application id "{target_bundle_id}" to activate\n'
            "delay 0.08\n"
            'tell application "System Events" to keystroke "v" using command down'
        )
    else:
        script = 'tell application "System Events" to keystroke "v" using command down'
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


def paste_text(text: str, target_bundle_id: str | None, config: dict[str, Any]) -> None:
    preserve = bool(config.get("preserve_clipboard", True))
    snapshot = capture_clipboard() if preserve else None
    set_clipboard(text)
    paste_clipboard(target_bundle_id)
    if preserve:
        time.sleep(max(0.0, float(config.get("clipboard_restore_delay_seconds", 0.35))))
        restore_clipboard(snapshot)


class WaveformView(NSView):
    def drawRect_(self, _rect: Any) -> None:
        widget = getattr(self, "widget", None)
        if widget is None:
            return

        width = float(widget.width)
        height = float(widget.height)
        NSColor.clearColor().setFill()
        NSBezierPath.bezierPathWithRect_(NSMakeRect(0, 0, width, height)).fill()

        pill_rect = NSMakeRect(1.0, 1.0, width - 2.0, height - 2.0)
        pill = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(pill_rect, 15.0, 15.0)
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.015, 0.015, 0.02, 0.88).setFill()
        pill.fill()
        NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 1.0, 1.0, 0.10).setStroke()
        pill.setLineWidth_(1.0)
        pill.stroke()

        bars = 26
        bar_width = 3.6
        gap = 3.2
        total_width = bars * bar_width + (bars - 1) * gap
        start_x = (width - total_width) / 2.0
        center_y = height / 2.0

        for idx in range(bars):
            t = idx / max(1, bars - 1)
            phase = widget.phase * 0.11 + idx * 0.34
            if widget.mode in {"recording", "locked"}:
                motion = 0.35 + 0.65 * ((np.sin(phase) + 1.0) / 2.0)
                center_weight = 0.66 + 0.34 * np.sin(np.pi * t)
                lock_lift = 0.10 if widget.mode == "locked" else 0.0
                bar_height = 4.0 + (widget.smooth_level + lock_lift) * (9.0 + 18.0 * motion * center_weight)
            elif widget.mode == "transcribing":
                motion = 0.25 + 0.75 * ((np.sin(phase * 1.45) + 1.0) / 2.0)
                bar_height = 4.0 + 10.0 * motion
            else:
                bar_height = 4.0

            if widget.mode == "locked":
                red = 0.62 + 0.20 * t
                green = 0.78 - 0.30 * t
                blue = 1.0
            else:
                red = 0.52 + 0.14 * t
                green = 0.82 - 0.24 * t
                blue = 1.0
            color = NSColor.colorWithCalibratedRed_green_blue_alpha_(red, green, blue, 0.96)
            x = start_x + idx * (bar_width + gap)
            bar_rect = NSMakeRect(x, center_y - bar_height / 2.0, bar_width, bar_height)
            bar = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(bar_rect, 1.8, 1.8)
            color.setFill()
            bar.fill()

    def tick_(self, _timer: Any) -> None:
        widget = getattr(self, "widget", None)
        if widget is not None:
            widget.tick()


class FloatingWidget:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.width = int(config["window_width"])
        self.height = int(config["window_height"])
        self.visible = False
        self.mode = "ready"
        self.target_level = 0.0
        self.smooth_level = 0.0
        self.phase = 0.0
        self.pending: queue.Queue[tuple[str, str | None, float | None]] = queue.Queue()

        self.app = NSApplication.sharedApplication()
        self.app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        self.panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, self.width, self.height),
            NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered,
            True,
        )
        self.panel.setLevel_(NSScreenSaverWindowLevel)
        self.panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
            | NSWindowCollectionBehaviorIgnoresCycle
            | NSWindowCollectionBehaviorStationary
            | NSWindowCollectionBehaviorTransient
        )
        self.panel.setBackgroundColor_(NSColor.clearColor())
        self.panel.setOpaque_(False)
        self.panel.setHasShadow_(False)
        self.panel.setIgnoresMouseEvents_(True)
        self.panel.setHidesOnDeactivate_(False)
        self.panel.setReleasedWhenClosed_(False)
        if hasattr(self.panel, "setFloatingPanel_"):
            self.panel.setFloatingPanel_(True)
        if hasattr(self.panel, "setWorksWhenModal_"):
            self.panel.setWorksWhenModal_(True)

        self.view = WaveformView.alloc().initWithFrame_(NSMakeRect(0, 0, self.width, self.height))
        self.view.widget = self
        self.panel.setContentView_(self.view)
        self.panel.orderOut_(None)
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0 / 30.0,
            self.view,
            "tick:",
            None,
            True,
        )

    def set_state(self, status: str, detail: str | None = None, level: float | None = None) -> None:
        self.pending.put((status, detail, level))

    def tick(self) -> None:
        had_pending = False
        while True:
            try:
                status, _detail, level = self.pending.get_nowait()
            except queue.Empty:
                break
            had_pending = True
            if level is not None:
                self.target_level = max(0.0, min(1.0, level))
            if status.startswith("Locked recording"):
                self.mode = "locked"
                self.show()
            elif status.startswith("Recording"):
                self.mode = "recording"
                self.show()
            elif status.startswith("Transcribing") or status.startswith("Error"):
                self.mode = "transcribing"
                self.show()
            else:
                self.mode = "ready"
                self.hide()

        if not self.visible and not had_pending:
            return

        self.phase = (self.phase + 1.0) % 10000.0
        target = self.target_level if self.mode in {"recording", "locked"} else 0.0
        self.smooth_level = self.smooth_level * 0.82 + target * 0.18
        if self.mode in {"recording", "locked"}:
            self.smooth_level = max(0.16, self.smooth_level)
        self.view.setNeedsDisplay_(True)

    def _screen_under_cursor(self) -> Any:
        point = NSEvent.mouseLocation()
        for screen in NSScreen.screens():
            frame = screen.frame()
            if (
                frame.origin.x <= point.x <= frame.origin.x + frame.size.width
                and frame.origin.y <= point.y <= frame.origin.y + frame.size.height
            ):
                return screen
        return NSScreen.mainScreen() or NSScreen.screens()[0]

    def _place_on_active_screen(self) -> None:
        screen = self._screen_under_cursor()
        visible = screen.visibleFrame()
        x = visible.origin.x + (visible.size.width - self.width) / 2.0
        bottom_margin = min(max(float(self.config["window_bottom_margin"]), 48.0), visible.size.height * 0.35)
        y = visible.origin.y + bottom_margin
        self.panel.setFrameOrigin_(NSMakePoint(x, y))
        log(f"widget placed at x={x:.0f}, y={y:.0f}, screen={visible.size.width:.0f}x{visible.size.height:.0f}")

    def show(self) -> None:
        if not self.visible:
            self._place_on_active_screen()
            self.panel.setAlphaValue_(0.94)
            self.panel.orderFrontRegardless()
            self.visible = True
            log("widget shown")

    def hide(self) -> None:
        if self.visible:
            self.panel.orderOut_(None)
            self.visible = False
            log("widget hidden")

    def mainloop(self) -> None:
        self.app.run()


class DictationDaemon:
    def __init__(self, widget: FloatingWidget, config: dict[str, Any]) -> None:
        self.widget = widget
        self.config = config
        self.hotkey = parse_hotkey(str(config["hotkey"]))
        self.lock_hotkey = parse_hotkey(str(config.get("lock_hotkey", "ctrl+cmd+option")))
        self.hotkey_text = hotkey_label(self.hotkey)
        self.lock_hotkey_text = hotkey_label(self.lock_hotkey)
        self.trigger_active = False
        self.lock_trigger_active = False
        self.recording_locked = False
        self.event_tap = None
        self.sample_rate = int(config["sample_rate"])
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.recording: Recording | None = None
        self.stream: sd.InputStream | None = None
        self.lock = threading.Lock()
        self.cancel_current = False
        self.model = None
        self.target_bundle_id: str | None = None
        self.control_socket_path = CONTROL_SOCKET_PATH

    def load_model(self) -> None:
        self.widget.set_state("Loading model...", str(MODEL_DIR))
        started = time.perf_counter()
        self.model = onnx_asr.load_model(
            "nemo-parakeet-tdt-0.6b-v2",
            path=MODEL_DIR,
            quantization="int8",
            providers=["CPUExecutionProvider"],
        )
        log(f"model loaded in {time.perf_counter() - started:.1f}s")
        self.widget.set_state(f"Ready. Hold {self.hotkey_text}")

    def start_keyboard_listener(self) -> None:
        thread = threading.Thread(target=self._run_event_tap, daemon=True)
        thread.start()

    def start_control_server(self) -> None:
        thread = threading.Thread(target=self._run_control_server, daemon=True)
        thread.start()

    def _run_control_server(self) -> None:
        self.control_socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self.control_socket_path.exists():
            self.control_socket_path.unlink()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self.control_socket_path))
        self.control_socket_path.chmod(0o600)
        server.listen(4)
        log(f"control socket listening: {self.control_socket_path}")
        while True:
            conn, _addr = server.accept()
            with conn:
                try:
                    request = conn.recv(4096).decode("utf-8").strip()
                    payload = json.loads(request or "{}")
                    response = self.handle_control_command(payload)
                except Exception as exc:  # noqa: BLE001
                    response = {"ok": False, "error": str(exc)}
                conn.sendall((json.dumps(response, ensure_ascii=True) + "\n").encode("utf-8"))

    def handle_control_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        command = str(payload.get("command") or "")
        if command == "status":
            return {
                "ok": True,
                "recording": self.recording is not None,
                "locked": self.recording_locked,
                "model_loaded": self.model is not None,
                "hotkey": self.hotkey_text,
                "lock_hotkey": self.lock_hotkey_text,
            }
        if command == "start":
            if self.recording is None:
                self.events.put(
                    (
                        "start",
                        {
                            "locked": bool(payload.get("locked", True)),
                            "target_bundle_id": payload.get("target_bundle_id"),
                        },
                    )
                )
            elif payload.get("locked"):
                self.events.put(("lock", None))
            return {"ok": True, "queued": "start"}
        if command == "stop":
            self.recording_locked = False
            self.events.put(("stop", None))
            return {"ok": True, "queued": "stop"}
        if command == "cancel":
            self.cancel_current = True
            self.recording_locked = False
            self.events.put(("stop", None))
            return {"ok": True, "queued": "cancel"}
        raise ValueError(f"unknown control command: {command}")

    def _run_event_tap(self) -> None:
        event_mask = CGEventMaskBit(kCGEventFlagsChanged) | CGEventMaskBit(kCGEventKeyDown)
        tap = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionDefault,
            event_mask,
            self._event_tap_callback,
            None,
        )
        if tap is None:
            log("CGEventTap creation failed; grant Accessibility and Input Monitoring permissions")
            self.widget.set_state("Error", "Grant Accessibility + Input Monitoring")
            return

        source = CFMachPortCreateRunLoopSource(None, tap, 0)
        if source is None:
            log("CGEventTap run loop source creation failed")
            self.widget.set_state("Error", "Hotkey monitor failed")
            return

        self.event_tap = tap
        CFRunLoopAddSource(CFRunLoopGetCurrent(), source, kCFRunLoopCommonModes)
        CGEventTapEnable(tap, True)
        log("keyboard CGEventTap started")
        CFRunLoopRun()

    def _event_tap_callback(self, _proxy: Any, event_type: int, event: Any, _refcon: Any) -> Any:
        try:
            if event_type in (kCGEventTapDisabledByTimeout, kCGEventTapDisabledByUserInput):
                if self.event_tap is not None:
                    CGEventTapEnable(self.event_tap, True)
                return event

            if event_type == kCGEventKeyDown:
                keycode = int(CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode))
                if keycode == KEY_ESC and self.recording is not None:
                    if self.recording_locked:
                        self.recording_locked = False
                    else:
                        self.cancel_current = True
                    self.events.put(("stop", None))
                    return None
                return event

            if event_type == kCGEventFlagsChanged:
                flags = int(CGEventGetFlags(event))
                pressed: set[str] = set()
                if flags & int(kCGEventFlagMaskCommand):
                    pressed.add("cmd")
                if flags & int(kCGEventFlagMaskAlternate):
                    pressed.add("option")
                if flags & int(kCGEventFlagMaskControl):
                    pressed.add("ctrl")

                lock_down = self.lock_hotkey.issubset(pressed)
                hold_down = self.hotkey.issubset(pressed)

                if lock_down and not self.lock_trigger_active:
                    self.lock_trigger_active = True
                    self.recording_locked = True
                    if self.recording is None and not self.trigger_active:
                        self.events.put(("start", {"locked": True}))
                    else:
                        self.events.put(("lock", None))
                    return event

                if self.lock_trigger_active and not lock_down:
                    self.lock_trigger_active = False

                if self.recording_locked:
                    if not hold_down:
                        self.trigger_active = False
                    return event

                if hold_down and not self.trigger_active:
                    self.trigger_active = True
                    self.events.put(("start", {"locked": False}))
                elif self.trigger_active and not hold_down:
                    self.trigger_active = False
                    self.events.put(("stop", None))

            return event
        except Exception as exc:  # noqa: BLE001
            log(f"CGEventTap callback failed: {exc}")
            return event

    def run_event_loop(self) -> None:
        while True:
            action, payload = self.events.get()
            try:
                if action == "start":
                    locked = bool(payload.get("locked")) if isinstance(payload, dict) else False
                    target_bundle_id = payload.get("target_bundle_id") if isinstance(payload, dict) else None
                    self.start_recording(locked=locked, target_bundle_id=target_bundle_id)
                elif action == "lock":
                    self.lock_recording()
                elif action == "stop":
                    self.stop_recording()
            except Exception as exc:  # noqa: BLE001
                log(f"{action} failed: {exc}")
                self.widget.set_state("Error", str(exc))

    def start_recording(self, locked: bool = False, target_bundle_id: str | None = None) -> None:
        with self.lock:
            if self.recording is not None:
                if locked:
                    self.recording_locked = True
                    self.widget.set_state("Locked recording...", "Esc to transcribe", 0.0)
                return
            self.cancel_current = False
            self.recording_locked = locked
            if target_bundle_id:
                self.target_bundle_id = target_bundle_id
            else:
                target_app = NSWorkspace.sharedWorkspace().frontmostApplication()
                self.target_bundle_id = str(target_app.bundleIdentifier()) if target_app is not None else None
            frames: list[np.ndarray] = []
            self.recording = Recording(frames=frames, started_at=time.perf_counter(), sample_rate=self.sample_rate)

            def callback(indata: np.ndarray, _frames: int, _time_info: Any, status: sd.CallbackFlags) -> None:
                if status:
                    log(f"audio status: {status}")
                mono = indata[:, 0].copy()
                frames.append(mono)
                rms = float(np.sqrt(np.mean(np.square(mono)))) if mono.size else 0.0
                status_text = "Locked recording..." if self.recording_locked else "Recording..."
                self.widget.set_state(status_text, level=min(1.0, rms * 24))

            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                callback=callback,
            )
            self.stream.start()
            log(f"recording started locked={locked}")
            if locked:
                self.widget.set_state("Locked recording...", "Esc to transcribe", 0.0)
            else:
                self.widget.set_state("Recording...", "Release hotkey to transcribe", 0.0)

    def lock_recording(self) -> None:
        with self.lock:
            if self.recording is None:
                return
            self.recording_locked = True
        log("recording locked")
        self.widget.set_state("Locked recording...", "Esc to transcribe", 0.0)

    def stop_recording(self) -> None:
        with self.lock:
            recording = self.recording
            stream = self.stream
            self.recording = None
            self.stream = None
            was_locked = self.recording_locked
            self.recording_locked = False
        if recording is None:
            return
        if stream is not None:
            stream.stop()
            stream.close()

        duration = time.perf_counter() - recording.started_at
        if self.cancel_current:
            log(f"recording cancelled locked={was_locked}")
            self.widget.set_state(f"Ready. Hold {self.hotkey_text}", "Cancelled", 0.0)
            return
        if duration < float(self.config["min_recording_seconds"]):
            log(f"recording too short: {duration:.2f}s")
            self.widget.set_state(f"Ready. Hold {self.hotkey_text}", "Too short", 0.0)
            return

        audio = np.concatenate(recording.frames) if recording.frames else np.array([], dtype=np.float32)
        if audio.size == 0:
            log(f"recording captured no samples: {duration:.2f}s")
            self.widget.set_state(f"Ready. Hold {self.hotkey_text}", "No microphone samples", 0.0)
            return
        if float(np.max(np.abs(audio))) == 0.0:
            log(f"recording captured silent audio: {duration:.2f}s, samples={audio.size}")
            self.widget.set_state(f"Ready. Hold {self.hotkey_text}", "No microphone signal", 0.0)
            return
        trimmed_audio, vad_stats = trim_audio_with_vad(audio, self.sample_rate, self.config)
        if trimmed_audio is None or trimmed_audio.size == 0:
            log(
                "recording skipped by vad: "
                f"reason={vad_stats.reason}, original={vad_stats.original_sec:.2f}s, "
                f"speech={vad_stats.speech_ms:.0f}ms, frames={vad_stats.speech_frames}/{vad_stats.total_frames}"
            )
            self.widget.set_state(f"Ready. Hold {self.hotkey_text}", "No speech", 0.0)
            return

        log(
            "recording stopped: "
            f"{duration:.2f}s wall, samples={audio.size}, vad={vad_stats.reason}, "
            f"audio={vad_stats.original_sec:.2f}s->{vad_stats.trimmed_sec:.2f}s, "
            f"speech={vad_stats.speech_ms:.0f}ms"
        )
        threading.Thread(target=self.transcribe_and_paste, args=(trimmed_audio, duration, vad_stats), daemon=True).start()

    def transcribe_and_paste(self, audio: np.ndarray, duration: float, vad_stats: VadStats) -> None:
        if self.model is None:
            self.load_model()
        audio_sec = audio.size / float(self.sample_rate) if self.sample_rate else duration
        self.widget.set_state("Transcribing...", f"{audio_sec:.1f}s audio", 0.0)
        with tempfile.TemporaryDirectory(prefix="macos-local-asr-") as tmp:
            wav_path = Path(tmp) / "dictation.wav"
            write_wav(wav_path, audio, self.sample_rate)
            started = time.perf_counter()
            result = self.model.recognize(wav_path, sample_rate=self.sample_rate)
            elapsed = time.perf_counter() - started
        raw_text = str(result).strip()
        runtime_config = load_config()
        self.config = runtime_config
        text = raw_text
        cleanup_elapsed = 0.0
        if raw_text and runtime_config.get("cleanup_enabled", False):
            self.widget.set_state("Cleaning transcript...", str(runtime_config.get("cleanup_model", "")), 0.0)
            cleanup_started = time.perf_counter()
            try:
                text = cleanup_text(raw_text, runtime_config)
                cleanup_elapsed = time.perf_counter() - cleanup_started
                log(
                    "cleanup complete: "
                    f"provider={runtime_config.get('cleanup_provider')}, "
                    f"model={runtime_config.get('cleanup_model')}, latency={cleanup_elapsed:.2f}s"
                )
            except CleanupError as exc:
                cleanup_elapsed = time.perf_counter() - cleanup_started
                text = raw_text
                log(f"cleanup failed, using raw transcript: {exc}")
        if text:
            log(
                "transcription complete: "
                f"{audio_sec:.2f}s audio, {elapsed:.2f}s asr latency, "
                f"{cleanup_elapsed:.2f}s cleanup latency, words={len(text.split())}"
            )
            if runtime_config.get("paste_into_active_app", True):
                paste_text(text, self.target_bundle_id, runtime_config)
            elif runtime_config.get("copy_to_clipboard", False):
                set_clipboard(text)
            self.write_history(text, duration, audio_sec, elapsed + cleanup_elapsed, vad_stats, raw_text=raw_text)
            self.widget.set_state(
                f"Ready. Hold {self.hotkey_text}",
                f"Pasted {len(text.split())} words in {elapsed + cleanup_elapsed:.2f}s",
                0.0,
            )
        else:
            log(f"transcription empty: {audio_sec:.2f}s audio, {elapsed:.2f}s latency")
            self.widget.set_state(f"Ready. Hold {self.hotkey_text}", "No transcript", 0.0)

    def write_history(
        self,
        text: str,
        duration: float,
        audio_sec: float,
        elapsed: float,
        vad_stats: VadStats,
        *,
        raw_text: str | None = None,
    ) -> None:
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "created_at": time.time(),
            "duration_sec": duration,
            "audio_sec": audio_sec,
            "latency_sec": elapsed,
            "text": text,
            "vad": {
                "enabled": vad_stats.enabled,
                "reason": vad_stats.reason,
                "original_sec": vad_stats.original_sec,
                "trimmed_sec": vad_stats.trimmed_sec,
                "speech_ms": vad_stats.speech_ms,
                "start_ms": vad_stats.start_ms,
                "end_ms": vad_stats.end_ms,
                "speech_frames": vad_stats.speech_frames,
                "total_frames": vad_stats.total_frames,
            },
        }
        if raw_text is not None and raw_text != text:
            payload["raw_text"] = raw_text
        with HISTORY_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def main() -> None:
    if "--test-ui" in sys.argv:
        config = load_config()
        widget = FloatingWidget(config)

        def drive_widget() -> None:
            started = time.perf_counter()
            while time.perf_counter() - started < 5.0:
                elapsed = time.perf_counter() - started
                level = 0.25 + 0.55 * ((np.sin(elapsed * 5.0) + 1.0) / 2.0)
                widget.set_state("Recording...", "UI smoke test", float(level))
                time.sleep(1.0 / 30.0)
            widget.set_state("Ready. Hold Command + Option", "UI smoke test complete", 0.0)
            time.sleep(0.25)
            widget.app.performSelectorOnMainThread_withObject_waitUntilDone_("terminate:", None, False)

        threading.Thread(target=drive_widget, daemon=True).start()
        log("ui smoke test started")
        widget.mainloop()
        log("ui smoke test ended")
        return

    if not MODEL_DIR.exists():
        raise SystemExit(f"Missing model directory: {MODEL_DIR}")
    config = load_config()
    widget = FloatingWidget(config)
    daemon = DictationDaemon(widget, config)
    threading.Thread(target=daemon.load_model, daemon=True).start()
    daemon.start_keyboard_listener()
    daemon.start_control_server()
    threading.Thread(target=daemon.run_event_loop, daemon=True).start()
    log("daemon started")
    widget.mainloop()
    log("daemon exited")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        log(f"fatal: {exc}")
        raise
