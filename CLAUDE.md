# imgforge — Claude Instructions

## What This Project Is

A Python library for local image generation using `diffusers` and PyTorch. No CLI. Pure Python API.

- Runs entirely on Apple Silicon (MPS) — no cloud, no API calls
- Default model is public, no HuggingFace token required
- Used as a dependency by other projects (e.g. `social-agent`)

## API

```python
from imgforge import generate

result = generate(prompts, output_dir="./output", model=None, hf_token=None)
# result.ok          bool
# result.images      list[Path]  — populated on success
# result.error_type  str | None  — "user_error" | "unexpected"
# result.error_message str | None
# result.traceback   str | None  — only on "unexpected"
```

`prompts` can be a `str` or `list[str]`.

## Architecture

```
imgforge/
├── __init__.py       # public API: generate()
├── orchestrator.py   # loads diffusers pipeline, runs inference, saves images
├── config.py         # Config dataclass + env loading
├── result.py         # GenerateResult dataclass
├── exceptions.py     # UserError, ImgForgeError
└── bug_report.py     # auto-file GitHub issues on unexpected errors
```

## How It Works

```
1. generate(prompts) called
2. load_config() reads HF_MODEL from env (default: runwayml/stable-diffusion-v1-5)
3. First call only:
   - Download model from HuggingFace Hub (~2.5GB, cached locally)
   - Load into GPU memory (float16, MPS)
   - enable_attention_slicing() to reduce memory pressure
4. For each prompt:
   - Run inference: pipeline(prompt, num_inference_steps=15)
   - Save PNG to output_dir/image_{i}.png
5. Return GenerateResult(ok=True, images=[...])
```

## Model Support

- `runwayml/stable-diffusion-v1-5` (~2.5GB, ~5-10s, default, public, no auth)
- `stabilityai/stable-diffusion-xl-base-1.0` (~6GB, ~10-20s, requires HF_TOKEN)
- `black-forest-labs/FLUX.1-schnell` (requires HF_TOKEN + quantization)

## Key Design Decisions

- **No CLI** — library only; callers use the Python API directly
- **MPS only** — hardcoded `_PIPELINE.to("mps")`; CUDA not implemented
- **Float16** — reduces memory, fits on 8GB M2
- **Safety checker disabled** — removes overhead
- **Global pipeline cache** — model loads once per process
- **No pytest/unit tests** — test by actually calling `generate()`

## Environment Variables

| Env var | Required | Default | Description |
|---|---|---|---|
| `HF_MODEL` | No | `runwayml/stable-diffusion-v1-5` | Model ID |
| `HF_TOKEN` | No | — | Only needed for gated models |

## Installation as a Dependency

```bash
# uv
uv add "imgforge @ git+https://github.com/DDecoene/imgforge.git"

# pip
pip install "imgforge @ git+https://github.com/DDecoene/imgforge.git"

# Local editable (when both repos on same machine)
uv add --editable ../imgforge
```

## Development Setup

```bash
git clone https://github.com/DDecoene/imgforge
cd imgforge
uv sync
```

## Testing

No unit tests. Test by calling generate() directly:

```python
from imgforge import generate
result = generate("a red panda on a surfboard")
# Expect: result.ok == True, output/image_0.png written in ~5-10s
```
