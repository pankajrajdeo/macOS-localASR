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

Current MVP features:

- status polling
- start locked recording
- start manual recording
- stop and paste
- cancel recording
- preserve clipboard toggle
- paste into active app toggle
- health check
- permissions shortcut
- worker restart
- basic settings tabs

Packaging as a signed `.app` and `.dmg` is still pending.
