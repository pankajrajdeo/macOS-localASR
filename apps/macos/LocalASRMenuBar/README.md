# LocalASR Menu-Bar MVP

SwiftUI menu-bar shell for macOS-localASR.

This package does not run ASR directly. It controls the installed Python worker
through:

- `~/bin/macos-local-asr`
- `~/Library/Application Support/macOS-localASR/control.sock`

Install the worker first from the repo root:

```bash
./install.sh
~/bin/macos-local-asr permissions
~/bin/macos-local-asr restart
```

Build and run the menu-bar app:

```bash
swift build --package-path apps/macos/LocalASRMenuBar
swift run --package-path apps/macos/LocalASRMenuBar
```

Build a `.app` bundle from the repo root:

```bash
python3 scripts/build_macos_app.py
open dist/LocalASR.app
```

Current MVP features:

- status polling
- start locked recording
- start manual recording
- stop and paste
- cancel recording
- start, stop, restart, and quit service controls
- preserve clipboard toggle
- paste into active app toggle
- optional ASR cleanup with Ollama or OpenAI-compatible APIs
- modifier-key hotkey recorder
- history search and stats
- health check
- permissions shortcut
- worker restart
- basic settings tabs

Use `Stop Service` to turn off the background worker while keeping the menu app
open. Use `Stop & Quit` to stop the worker and close the menu app.

Enhance mode is off by default. If enabled, the visible cleanup prompt is only a
style guide; the app adds a hidden task/safety prompt so transcript text is
treated as data to clean, not as an instruction to answer.

Signing, notarization, `.dmg` packaging, and the native non-Python ASR worker are
still pending.
