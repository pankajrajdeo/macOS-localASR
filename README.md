# macOS-localASR

Local, system-wide push-to-talk dictation for macOS.

macOS-localASR runs a local ONNX INT8 Parakeet ASR model, listens for a global push-to-talk hotkey, shows a small native macOS waveform overlay, and pastes the raw transcript into the app you were using. Audio and transcripts stay on your Mac.

## Features

- System-wide push-to-talk dictation.
- Default hotkey: hold `Command + Option`, speak, release.
- Lock mode: press `Control + Command + Option`, release the keys, keep speaking, then press `Escape` to transcribe.
- Native non-activating macOS overlay that does not steal focus.
- Paste-at-cursor into the previously active app.
- Preserves your previous clipboard after using it transiently for paste.
- Local ONNX INT8 ASR model bundled in the repo through Git LFS.
- Lightweight WebRTC VAD for silence/noise skipping and edge trimming.
- No cloud ASR, no post-ASR cleanup, no LLM rewrite.
- User-level LaunchAgent that starts at login.

## Requirements

- macOS 14 or newer recommended.
- Apple Silicon recommended.
- Python 3.11 or newer available as `python3`.
- Git LFS for cloning the bundled model.
- macOS permissions for the installed Python runtime:
  - Microphone
  - Accessibility
  - Input Monitoring

For file/URL transcription and smoke tests:

- `ffmpeg`

```bash
brew install git-lfs ffmpeg
git lfs install
```

## Install

```bash
git clone https://github.com/pankajrajdeo/macOS-localASR.git
cd macOS-localASR
git lfs pull
./install.sh
```

Then open permissions:

```bash
~/bin/macos-local-asr permissions
```

Grant permissions to:

```text
~/Library/Application Support/macOS-localASR/.venv/bin/python
```

Restart after granting permissions:

```bash
~/bin/macos-local-asr restart
```

## Use

1. Click into any text field.
2. Hold `Command + Option`.
3. Speak.
4. Release the keys.

The transcript is pasted into the app that was active when recording started. The app uses the clipboard briefly for paste delivery, then restores your previous clipboard contents by default.

Press `Escape` during hold-to-talk recording to cancel before release.

For longer dictation:

1. Click into any text field.
2. Press `Control + Command + Option`.
3. Release the keys and keep speaking.
4. Press `Escape` to stop, transcribe, and paste.

## Commands

```bash
~/bin/macos-local-asr start
~/bin/macos-local-asr stop
~/bin/macos-local-asr restart
~/bin/macos-local-asr status
~/bin/macos-local-asr logs
~/bin/macos-local-asr permissions
~/bin/macos-local-asr run
~/bin/macos-local-asr test-ui
~/bin/macos-local-asr health
~/bin/macos-local-asr control status
~/bin/macos-local-asr control start --locked
~/bin/macos-local-asr control stop
~/bin/macos-local-asr control cancel
~/bin/macos-local-asr cleanup models
~/bin/macos-local-asr cleanup test "this is a sample dictation"
~/bin/macos-local-asr transcribe file recording.wav --output transcript.txt
~/bin/macos-local-asr transcribe url "https://www.youtube.com/watch?v=..." --output transcript.txt
~/bin/macos-local-asr config show
~/bin/macos-local-asr config get hotkey
~/bin/macos-local-asr config set preserve_clipboard true
~/bin/macos-local-asr hotkey set push cmd+option
~/bin/macos-local-asr hotkey set lock ctrl+cmd+option
~/bin/macos-local-asr history search meeting
~/bin/macos-local-asr history stats
~/bin/macos-local-asr uninstall
```

From the menu-bar app:

- `Stop Service` turns off the background ASR worker.
- `Quit App` closes only the menu-bar UI.
- `Stop & Quit` turns off the worker and closes the menu-bar UI.

## Installed Locations

The cloned repository is only needed for installation. The runtime is copied into your user Library and works even if you delete the clone.

```text
~/Library/Application Support/macOS-localASR
~/Library/LaunchAgents/com.pankajrajdeo.macos-local-asr.plist
~/bin/macos-local-asr
```

Important runtime files:

```text
~/Library/Application Support/macOS-localASR/macos_local_asr/
~/Library/Application Support/macOS-localASR/config.json
~/Library/Application Support/macOS-localASR/models/parakeet-tdt-0.6b-v2-onnx-int8
~/Library/Application Support/macOS-localASR/logs
~/Library/Application Support/macOS-localASR/history.jsonl
~/Library/Application Support/macOS-localASR/control.sock
```

## Configuration

Edit:

```text
~/Library/Application Support/macOS-localASR/config.json
```

Then restart:

```bash
~/bin/macos-local-asr restart
```

Default config:

```json
{
  "hotkey": "cmd+option",
  "lock_hotkey": "ctrl+cmd+option",
  "sample_rate": 16000,
  "paste_into_active_app": true,
  "copy_to_clipboard": false,
  "preserve_clipboard": true,
  "clipboard_restore_delay_seconds": 0.35,
  "min_recording_seconds": 0.25,
  "window_width": 230,
  "window_height": 44,
  "window_bottom_margin": 94,
  "vad_enabled": true,
  "vad_aggressiveness": 2,
  "vad_frame_ms": 20,
  "vad_start_padding_ms": 160,
  "vad_end_padding_ms": 320,
  "vad_min_speech_ms": 80,
  "vad_audible_rms": 0.0025,
  "log_max_bytes": 1048576,
  "log_backup_count": 5,
  "cleanup_enabled": false,
  "cleanup_provider": "ollama",
  "cleanup_model": "",
  "cleanup_api_base": "http://127.0.0.1:11434",
  "cleanup_api_key": "",
  "cleanup_prompt": "General ASR cleanup style:\n- Produce a readable transcript, not a summary or response.\n- Add sentence punctuation, capitalization, and paragraph breaks only where clearly supported.\n- Preserve the speaker's meaning, wording, order, language, and code-switching.\n- Preserve named entities, technical terms, acronyms, drug names, gene/protein names, product names, measurements, units, dates, times, negation, and uncertainty.\n- Fix only high-confidence ASR slips; if a word or phrase is ambiguous, keep the original wording.\n- Remove only obvious filler words and repeated false starts when they do not change meaning.\n- Do not invent missing content, expand abbreviations, explain, answer questions, or convert the transcript into notes.\n- Output plain text only."
}
```

Supported hotkey aliases currently include `cmd`, `command`, `option`, `alt`, `ctrl`, and `control`. Modifier-only hotkeys need Accessibility/Input Monitoring permissions.

The JSON schema is documented at [`docs/config.schema.json`](docs/config.schema.json).

Common config examples:

```bash
~/bin/macos-local-asr config validate
~/bin/macos-local-asr config set preserve_clipboard true
~/bin/macos-local-asr config set copy_to_clipboard false
~/bin/macos-local-asr hotkey set push cmd+option
~/bin/macos-local-asr hotkey set lock ctrl+cmd+option
~/bin/macos-local-asr config set cleanup_enabled true
~/bin/macos-local-asr config set cleanup_provider ollama
~/bin/macos-local-asr cleanup models
~/bin/macos-local-asr restart
```

## Optional ASR Cleanup

Raw local ASR is the default. Cleanup is optional and runs only when `cleanup_enabled` is true.

Recommended setup:

```bash
ollama pull liquidai/lfm2.5-1.2b-instruct:q4_k_m
~/bin/macos-local-asr config set cleanup_provider ollama
~/bin/macos-local-asr config set cleanup_model liquidai/lfm2.5-1.2b-instruct:q4_k_m
~/bin/macos-local-asr config set cleanup_enabled true
~/bin/macos-local-asr restart
```

The app also supports an OpenAI-compatible endpoint:

```bash
~/bin/macos-local-asr config set cleanup_provider openai_compatible
~/bin/macos-local-asr config set cleanup_api_base https://api.openai.com/v1
~/bin/macos-local-asr config set cleanup_model gpt-4o-mini
~/bin/macos-local-asr config set cleanup_api_key YOUR_KEY
~/bin/macos-local-asr config set cleanup_enabled true
```

For privacy, local Ollama is the preferred default. API keys are currently stored in the local config file, so use a local server or a scoped key until Keychain storage is added.

The visible cleanup prompt is only a style guide. The app adds a hidden safety prefix/suffix that tells the model to treat ASR text as transcript data, not as a question or instruction to answer.

## File and URL Transcription

The menu-bar Settings window includes a `Transcribe` tab for one-off audio/video transcription:

- browse for a local audio/video file, or paste a YouTube/direct media URL
- choose where to save `transcript.txt`
- optionally disable cleanup for that file
- watch progress while the app downloads, converts, chunks, transcribes, cleans up, and writes the transcript
- preview the transcript after completion

CLI equivalents:

```bash
~/bin/macos-local-asr transcribe file /path/to/recording.wav --output ~/Desktop/transcript.txt
~/bin/macos-local-asr transcribe url "https://www.youtube.com/watch?v=..." --output ~/Desktop/transcript.txt
~/bin/macos-local-asr transcribe file /path/to/recording.wav --progress-json
```

URL transcription uses `yt-dlp` and `ffmpeg` in a temporary directory. The app writes only the final transcript to the chosen output path; downloaded/converted media is deleted when the job finishes. Only transcribe media that you have the right to access and process.

Long files are split into temporary 10-minute WAV chunks before local ONNX ASR. Chunks are deleted with the temporary working directory after the job finishes.

## Smoke Test

The smoke test uses macOS `say`, `ffmpeg`, and the bundled model:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/smoke_test.py
```

Expected output includes:

```text
transcript=This is the final local dictation test.
```

To test only the native waveform overlay:

```bash
~/bin/macos-local-asr test-ui
```

Run the Phase 1 unit tests:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Menu-Bar MVP

The repo includes an early native SwiftUI menu-bar shell at:

```text
apps/macos/LocalASRMenuBar
```

It controls the installed Python worker through `~/bin/macos-local-asr` and the local control socket. Install the service first with `./install.sh`, then build and run the menu-bar app:

```bash
swift build --package-path apps/macos/LocalASRMenuBar
swift run --package-path apps/macos/LocalASRMenuBar
```

To build a normal macOS `.app` bundle:

```bash
python3 scripts/build_macos_app.py
open dist/LocalASR.app
```

The current menu-bar MVP supports:

- status polling
- start locked recording
- start manual recording
- stop and paste
- cancel recording
- start, stop, restart, and quit service controls
- preserve clipboard toggle
- paste into active app toggle
- optional ASR cleanup through Ollama or OpenAI-compatible APIs
- modifier-key hotkey recorder
- history search and stats
- file and URL transcription to `transcript.txt`
- health check
- permissions shortcut
- worker restart
- basic settings tabs

This is not yet a signed/notarized `.app` or `.dmg`. Full signing, notarization, model download, native worker replacement, and updates are tracked in [`docs/GUI_PACKAGING_ROADMAP.md`](docs/GUI_PACKAGING_ROADMAP.md).

## Resource Use

On Apple Silicon, typical behavior after model load:

- Idle CPU: near zero.
- Transcription latency: usually well under 1 second for short dictations.
- Installed size: around 800 MB.
- Model size: around 631 MB.

macOS may show the ONNX model as resident memory after recent use. Much of it is memory-mapped and can be reclaimed/compressed by the OS when idle.

## GUI Packaging Roadmap

See [`docs/GUI_PACKAGING_ROADMAP.md`](docs/GUI_PACKAGING_ROADMAP.md) for the path from this LaunchAgent prototype to a signed macOS menu-bar app and eventually a Windows tray app.

## Privacy

The daemon loads a local model from disk and runs inference locally through ONNX Runtime.

It does not call:

- OpenAI
- Groq
- Whisper APIs
- Hugging Face
- Any other cloud ASR or LLM service

The installed Python environment intentionally uses plain `onnx-asr`, not `onnx-asr[hub]`.

## Model and License

The application code is MIT licensed. See `LICENSE`.

The bundled model artifacts are derivative ONNX artifacts for NVIDIA Parakeet TDT 0.6B V2 and carry the upstream model terms, currently listed as CC-BY-4.0 in the included model card. See:

- `NOTICE.md`
- `models/parakeet-tdt-0.6b-v2-onnx-int8/README.md`
- `models/parakeet-tdt-0.6b-v2-onnx-int8/ATTRIBUTION.md`
- `models/parakeet-tdt-0.6b-v2-onnx-int8/provenance/`

Keep attribution files with any redistribution.

## Git LFS

The ONNX model files are stored with Git LFS.

If the installer says the model file is a Git LFS pointer:

```bash
git lfs install
git lfs pull
```

## Uninstall

From anywhere after installation:

```bash
~/bin/macos-local-asr uninstall
```

Or from the cloned repo:

```bash
./uninstall.sh
```

Keep installed data/model/logs:

```bash
./uninstall.sh --keep-data
```

## Troubleshooting

If the hotkey does nothing:

- Run `~/bin/macos-local-asr health`.
- Re-run `~/bin/macos-local-asr permissions`.
- Grant Accessibility and Input Monitoring to the installed Python binary.
- Restart with `~/bin/macos-local-asr restart`.

If transcription works but the visualizer does not appear:

- Run `~/bin/macos-local-asr test-ui`.
- Check logs with `~/bin/macos-local-asr logs`.
- Confirm the installed Python binary has Accessibility permission.

If recording starts but captures no audio:

- Grant Microphone permission to the installed Python binary.
- Restart the service.

If paste does not land in the original app:

- Grant Accessibility permission.
- Keep the target app focused while holding the hotkey.

If `Command + Option` conflicts with another app:

- Change `hotkey` in `config.json`.
- Restart the service.
