---
license: cc-by-4.0
pipeline_tag: automatic-speech-recognition
tags:
  - onnx
  - automatic-speech-recognition
  - parakeet
  - fp32
  - fp16
  - int8
---

# Canonical Parakeet ONNX Weights

Canonical ONNX packaging for:

- FP32
- FP16 (generated from FP32)
- INT8 (upstream when available)
- `nemo128.onnx` rebuilt from `onnx-asr/preprocessors/nemo.py`

Source baseline: `istupakov/parakeet-tdt-0.6b-v2-onnx`
Target repo: `ysdede/parakeet-tdt-0.6b-v2-onnx`

See `ATTRIBUTION.md` and `provenance/manifest.json` for provenance details.
