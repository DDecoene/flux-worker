# imgforge — Claude Instructions

## What This Project Is

A Python library for local image generation using `diffusers` and PyTorch. No CLI. Pure Python API.

- Uses Stable Diffusion v1.5 — fits in 8GB RAM, runs on Apple Silicon (MPS)
- No cloud, no API calls, no tokens required
- Used as an editable dependency by `social-agent` (sibling repo)

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
├── orchestrator.py   # loads StableDiffusionPipeline, runs inference, saves images
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
   - Load into GPU memory with float32 on MPS
   - enable_attention_slicing() to reduce MPS memory pressure
4. For each prompt:
   - Run inference: pipeline(prompt, num_inference_steps=20)
   - Output size: 1280×720 (landscape, for social media)
   - Save PNG to output_dir/image_{i}.png
5. Return GenerateResult(ok=True, images=[...])
```

## Key Design Decisions

- **float32 on MPS, not float16** — float16 produces black images on Apple Silicon with SD v1.5
- **StableDiffusionPipeline** — SD v1.5 fits in 8GB; FLUX.1 requires 24GB+
- **1280×720 output** — landscape format for social media use
- **Safety checker disabled** — removes overhead
- **No CLI** — library only; callers use the Python API directly
- **MPS only** — hardcoded `_PIPELINE.to("mps")`; CUDA not implemented
- **Global pipeline cache** — model loads once per process, subsequent calls are instant
- **No pytest/unit tests** — test by running `python test_e2e.py`

## Environment Variables

| Env var | Required | Default | Description |
|---|---|---|---|
| `HF_MODEL` | No | `runwayml/stable-diffusion-v1-5` | Model ID |
| `HF_TOKEN` | No | — | HuggingFace token (for gated models) |

## Installation as a Dependency

```bash
# uv — from GitHub
uv add "imgforge @ git+https://github.com/DDecoene/imgforge.git"

# uv — local editable (when both repos on same machine)
uv add --editable ../imgforge

# pip
pip install "imgforge @ git+https://github.com/DDecoene/imgforge.git"
```

## Development Setup

```bash
git clone https://github.com/DDecoene/imgforge
cd imgforge
uv sync
```

## Testing

No unit tests. Run the e2e test:

```bash
python test_e2e.py
# Expect: e2e_output/image_0.png written, result.ok == True
```
