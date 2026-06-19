# Security and Privacy

macOS-localASR is intended to run fully locally.

The daemon:

- records only while the push-to-talk hotkey is held;
- loads the bundled local ONNX model from disk;
- uses local WebRTC VAD;
- writes local logs and history under `~/Library/Application Support/macOS-localASR`;
- does not call cloud ASR, cloud LLMs, Hugging Face, OpenAI, Groq, or any other network service.

macOS permissions are still sensitive. The installed Python runtime needs:

- Microphone, to record audio;
- Accessibility, to paste into the active app;
- Input Monitoring, to detect the global modifier hotkey.

Review `src/macos_local_asr/daemon.py` and `scripts/install.py` before installing on a managed or work device.

To report a security issue, open a private advisory or contact the repository owner.
