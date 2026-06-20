# GUI and Packaging Roadmap

This project currently ships as a Python-based user LaunchAgent with a native
macOS waveform HUD. That is good for proving the ASR pipeline, but a consumer
app should become a signed tray/menu-bar application with first-run setup,
settings, updates, and model management.

## Product Target

The useful baseline is not a generic transcription demo. It should be a small
offline dictation utility that works anywhere the cursor is active.

Core promise:

- Local-first dictation.
- Fast enough to replace typing.
- No account for local mode.
- No cloud ASR by default.
- Clipboard preservation.
- Reliable paste-at-cursor.
- Minimal idle CPU.
- Clear permissions onboarding.

## Original UI Direction

The UI should not copy another dictation app. The product category has common
needs, but the visual design should be ours: compact, native, quiet, and
trustworthy.

Design principles:

- Native first: use platform controls, SF Symbols on macOS, and standard menu
  bar/tray conventions.
- Status before settings: the first thing a user sees should be whether the app
  is ready, recording, transcribing, missing permissions, or missing models.
- One primary action: record now. Everything else is secondary.
- No dashboard heaviness: statistics and history should be useful, not the main
  surface.
- No decorative interface chrome: this is a productivity utility, not a media
  app.
- No hidden privacy tradeoffs: local/raw mode, enhancement mode, and clipboard
  behavior must be explicit.

### Proposed macOS Menu-Bar Popover

Use a narrow popover with four zones.

1. Status header:
   - App name and current state.
   - Small live waveform when recording.
   - Model state: ready, loading, missing, error.

2. Record controls:
   - `Start Recording` / `Stop and Paste`.
   - `Push-to-talk` hotkey label.
   - `Locked recording` hotkey label.
   - `Cancel current recording` when active.

3. Mode toggles:
   - Preserve clipboard.
   - Auto-stop on silence.
   - Enhance transcript.
   - Insert punctuation commands.

4. Utility links:
   - History.
   - Prompts.
   - Settings.
   - Check permissions.
   - Restart worker.
   - Quit.

The popover should be functional, not a clone of any reference. Use our own
spacing, labels, icon choices, and information hierarchy.

### Settings Windows

Settings should use separate native windows/tabs rather than stuffing everything
into the menu popover.

General:

- Launch at login.
- Preserve clipboard.
- Paste into active app.
- Keep transcript history.
- Auto-stop behavior.

Hotkeys:

- Push-to-talk.
- Toggle/locked recording.
- Cancel.
- Record new hotkey.
- Reset defaults.

Models:

- ASR model installed status.
- Optional enhancement model installed status.
- Download, verify, remove.
- CPU/RAM estimate for each optional model.

Prompts:

- Raw transcript.
- Quick Note.
- Email.
- Meeting Notes.
- Code / Developer.
- Custom.

History:

- Search.
- Copy.
- Reinsert.
- Delete.
- Export JSON/CSV.

### Recording HUD

Keep the HUD separate from the menu-bar popover.

The HUD should stay tiny and focus-safe:

- Small bottom-center waveform.
- Different tint for locked mode.
- Subtle transcribing state.
- No text unless there is an error.
- Never steals focus.
- Never becomes clickable.

This avoids the most common system-wide dictation bug: losing the insertion
cursor in the target app.

## Current Status

Implemented:

- Local ONNX INT8 Parakeet v2 ASR.
- System-wide push-to-talk.
- Locked long-dictation mode.
- Native non-activating waveform HUD.
- WebRTC VAD trimming.
- Clipboard-preserving paste.
- User LaunchAgent install.
- Git LFS model bundling.

Missing for a proper product:

- Menu-bar UI.
- Settings window.
- Hotkey recorder UI.
- Permission status UI.
- History browser.
- Optional local enhancement mode.
- File transcription.
- Signed/notarized macOS packaging.
- Windows tray packaging.
- Auto-update.

## Recommended Architecture

### Phase 1: macOS Native App

Build a SwiftUI menu-bar app first.

Use:

- `MenuBarExtra` for the menu-bar icon and popover.
- SwiftUI settings windows for Hotkeys, Prompts, History, and About.
- A small local service layer that starts/stops the existing ASR worker.
- Sparkle for app updates.
- Developer ID signing and notarization for distribution outside the App Store.

Keep the ASR worker process separate from the GUI process. The GUI should be
responsible for state, permissions, settings, and UX. The worker should be
responsible for audio capture, ASR, VAD, paste, and model loading.

Suggested process boundary:

- `macos-local-asr.app`: native SwiftUI shell.
- `asr-worker`: bundled helper process.
- IPC: local Unix domain socket or XPC.

This keeps crashes isolated. It also makes it easier to replace the Python
worker later without rewriting the UI.

### Phase 2: Replace Python Worker

For a polished app, avoid shipping a Python virtualenv long term.

Best long-term options:

- Rust worker with `onnxruntime` for macOS and Windows.
- Swift worker with ONNX Runtime or Core ML on macOS only.
- C++ worker if maximum control is needed.

Rust is the best cross-platform core because the same worker can run under a
macOS menu-bar app and a Windows tray app.

### Phase 3: Windows App

Build Windows after the macOS product is stable.

Use:

- Windows tray app with WinUI 3, WPF, or Tauri.
- Global hotkeys via Windows APIs.
- Microphone capture through WASAPI.
- Text insertion through UI Automation or clipboard-preserving paste.
- Same Rust/ONNX worker as macOS if Phase 2 is complete.

Windows should not be the first packaging target unless the worker is moved out
of Python. Shipping a Python ASR app on Windows is possible, but install size,
driver issues, antivirus false positives, and code signing are harder.

## Enhancement Mode

Default should remain raw ASR. It is fast, local, and lightweight.

Add enhancement as an optional mode:

- Off by default.
- Local only by default.
- Clear memory after idle.
- Preserve meaning over style.
- Never silently summarize unless the selected prompt asks for it.

Recommended model strategy:

- Use raw ASR for normal dictation.
- Use `liquidai/lfm2.5-350m:q4_k_m` for lightweight cleanup:
  punctuation, capitalization, minor grammar fixes, filler trimming.
- Use `liquidai/lfm2.5-1.2b-instruct:q4_k_m` for custom prompts:
  emails, meeting notes, code review, summaries, transformations.

Do not fine-tune first. Prompt templates and evaluation are faster and safer.
Fine-tune only after collecting enough failure cases.

## ASR Fine-Tuning

Do not start with ASR fine-tuning.

Better first steps:

- Build an accent evaluation set.
- Add domain vocabulary and custom word boosting if the backend supports it.
- Compare Parakeet v2, v3, and future small ASR models.
- Add optional post-ASR cleanup for punctuation and obvious errors.

Fine-tune ASR only if:

- We have at least hundreds of high-quality labeled clips for target accents.
- The license permits the fine-tuning and redistribution path.
- Evaluation shows the current model consistently fails in ways cleanup cannot
  fix.

For Indian-accent robustness, curated test data and model selection will likely
pay off before fine-tuning.

## High-Value Feature Differentiators

Prioritize:

- Pause detection / auto-stop for hands-free dictation.
- Internal audio transcription as a separate explicit mode.
- App-specific prompts.
- Developer mode for Cursor, VS Code, terminals, and issue trackers.
- Spoken formatting commands:
  new line, bullet, numbered list, comma, period, open paren, close paren.
- Local history with fast search.
- Bring-your-own model folder for advanced users.

Avoid early feature overload:

- Multi-agent workflows.
- Cloud sync.
- Team collaboration.
- Complex prompt marketplaces.
- Heavy always-on LLMs.

## Distribution

macOS:

- Build `.app`.
- Sign with Developer ID.
- Notarize with Apple.
- Ship `.dmg`.
- Use Sparkle for updates.
- First-run model download to `~/Library/Application Support/macOS-localASR`.

Windows:

- Build signed `.msi` or `.exe` installer.
- Install app under `%LocalAppData%` or `Program Files`.
- Store models under `%LocalAppData%/macOS-localASR` or a renamed product path.
- Add tray startup entry.
- Use Windows code signing to avoid SmartScreen friction.

Models:

- Do not require Git LFS for normal users.
- For public releases, download models from GitHub Releases, Hugging Face, or a
  controlled CDN.
- Verify SHA256 before first use.
- Let users remove optional enhancement models.

## Near-Term Repo Milestones

1. Add CLI config commands for hotkeys and clipboard behavior. Done.
2. Add menu-bar MVP for macOS.
3. Add history viewer.
4. Add optional local enhancement mode through Ollama.
5. Add file transcription without diarization.
6. Add internal audio transcription research spike.
7. Replace Python worker with Rust/ONNX worker.
8. Package signed macOS release.
9. Start Windows tray app.

## Implementation Plan

### Milestone 1: Stabilize Current Prototype

Goal: make the existing installed service reliable enough for daily use.

Status: implemented in the Python/LaunchAgent prototype.

Tasks:

- Add CLI commands. Done:
  - `config get`.
  - `config set`.
  - `hotkey set`.
  - `history search`.
- Add a JSON schema for `config.json`. Done.
- Add a local health command that checks model files, permissions, and worker
  state. Done.
- Add tests for clipboard preservation, VAD trimming, and hotkey parsing. Done.
- Add log rotation. Done.

### Milestone 2: macOS Menu-Bar MVP

Goal: ship a real `.app` shell without replacing the worker yet.

Tasks:

- Create `apps/macos/LocalASR.xcodeproj`.
- Build a SwiftUI `MenuBarExtra` app.
- Add first-run permission onboarding.
- Add a status popover with recording controls.
- Add settings tabs for General and Hotkeys.
- Start/stop the existing worker from the app.
- Communicate with the worker over a local socket.
- Keep the existing Python worker bundled for this milestone.

### Milestone 3: Native Settings and History

Goal: make it usable by non-technical users.

Tasks:

- Hotkey recorder UI.
- History window with search/copy/delete.
- Permissions diagnostic panel.
- Model status/download panel.
- Basic usage statistics from local history.
- Export/import settings.

### Milestone 4: Optional Enhancement Mode

Goal: improve text only when the user explicitly asks for it.

Tasks:

- Add enhancement toggle.
- Add prompt templates.
- Add Ollama adapter.
- Support `lfm2.5-350m` as the default lightweight cleanup model.
- Support `lfm2.5-1.2b-instruct` for heavier custom prompts.
- Add idle unload behavior for the enhancement model.
- Evaluate latency, RAM, and text quality before enabling by default.

### Milestone 5: Native Worker

Goal: remove the Python runtime from packaged releases.

Tasks:

- Create `crates/asr-worker`.
- Port config, VAD, recording, and paste IPC contracts.
- Run ONNX Runtime from Rust.
- Keep SwiftUI app as the macOS shell.
- Keep model files outside the app bundle in Application Support.
- Maintain the Python worker only as a development fallback.

### Milestone 6: Signed macOS Release

Goal: distribute a normal installable app.

Tasks:

- Developer ID signing.
- Notarization.
- DMG build.
- First-run model download.
- SHA256 verification.
- Sparkle updates.
- Crash/log collection only if the user explicitly opts in.

### Milestone 7: Windows Tray App

Goal: reuse the native worker and add Windows UI.

Tasks:

- Tray app shell.
- Global hotkeys.
- WASAPI microphone capture.
- Clipboard-preserving paste.
- Windows installer.
- Code signing.
- Model download and verification.
