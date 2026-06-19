# Attribution and Licensing

This repository packages derivative ONNX artifacts for Parakeet ASR.

## Upstream Sources

- Base model family: NVIDIA Parakeet (CC-BY-4.0)
- ONNX conversion baseline: `istupakov/parakeet-tdt-0.6b-v2-onnx` (snapshot: `0bbb45a3365852604aef28b538a8f066f4ccaa85`)
- Preprocessor source rebuilt from local `onnx-asr/preprocessors/nemo.py`

## Included Derivatives

- FP16 models generated from FP32 (`encoder-model.onnx`, `decoder_joint-model.onnx`)
- FP16 cast-fix post-processing applied for ONNX Runtime compatibility
- Rebuilt preprocessor exported as `nemo128.onnx`

## Publication Notes

- Preserve upstream licensing and attribution terms.
- Keep model card attribution to NVIDIA and conversion/tooling provenance.
- Do not remove this file when publishing.

Generated at: 2026-02-23T20:19:04.614042+00:00
