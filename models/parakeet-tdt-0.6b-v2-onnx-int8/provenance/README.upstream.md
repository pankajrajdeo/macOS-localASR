---
license: cc-by-4.0
language:
- en
base_model:
- nvidia/parakeet-tdt-0.6b-v2
pipeline_tag: automatic-speech-recognition
tags:
- automatic-speech-recognition
- asr
- onnx
- onnx-asr
---

NVIDIA Parakeet TDT 0.6B V2 (En) [model](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2) converted to ONNX format for [onnx-asr](https://github.com/istupakov/onnx-asr).

Install onnx-asr
```shell
pip install onnx-asr[cpu,hub]
```

Load Parakeet TDT model and recognize wav file
```py
import onnx_asr
model = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v2")
print(model.recognize("test.wav"))
```

Code for models export
```py
import nemo.collections.asr as nemo_asr
from pathlib import Path

model = nemo_asr.models.ASRModel.from_pretrained("nvidia/parakeet-tdt-0.6b-v2")

onnx_dir = Path("nemo-onnx")
onnx_dir.mkdir(exist_ok=True)
model.export(str(Path(onnx_dir, "model.onnx")))

with Path(onnx_dir, "vocab.txt").open("wt") as f:
    for i, token in enumerate([*model.tokenizer.vocab, "<blk>"]):
        f.write(f"{token} {i}\n")
```