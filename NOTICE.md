# Notices

## Code

The macOS-localASR application code is released under the MIT License. See `LICENSE`.

## Included ASR Model

This repository includes INT8 ONNX model artifacts for NVIDIA Parakeet TDT 0.6B V2.

- Base model family: NVIDIA Parakeet TDT 0.6B V2
- Base model license: CC-BY-4.0
- ONNX conversion baseline: `istupakov/parakeet-tdt-0.6b-v2-onnx`
- Packaged model path: `models/parakeet-tdt-0.6b-v2-onnx-int8`

The model files are derivative ONNX artifacts and are distributed under the upstream model terms. Keep the model README, attribution, and provenance files with any redistribution.

Model attribution files included in this repo:

- `models/parakeet-tdt-0.6b-v2-onnx-int8/README.md`
- `models/parakeet-tdt-0.6b-v2-onnx-int8/ATTRIBUTION.md`
- `models/parakeet-tdt-0.6b-v2-onnx-int8/provenance/`

## VAD

Voice activity detection is provided by WebRTC VAD through `webrtcvad-wheels`.
