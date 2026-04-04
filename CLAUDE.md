# imgforge — Claude Instructions

## What This Project Is

A Python library for local image generation using `diffusers` and PyTorch. No CLI. Pure Python API.

- Uses FLUX.1-schnell by default — fast, high quality, public (no HF_TOKEN required)
- Runs entirely on Apple Silicon (MPS) — no cloud, no API calls
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
├── orchestrator.py   # loads FluxPipeline, runs inference, saves images
├── config.py         # Config dataclass + env loading
├── result.py         # GenerateResult dataclass
├── exceptions.py     # UserError, ImgForgeError
└── bug_report.py     # auto-file GitHub issues on unexpected errors
```

## How It Works

```
1. generate(prompts) called
2. load_config() reads HF_MODEL from env (default: black-forest-labs/FLUX.1-schnell)
3. First call only:
   - Download model from HuggingFace Hub (~24GB, cached locally)
   - Load into GPU memory (bfloat16 on MPS — float16 produces black images with FLUX)
   - enable_attention_slicing() to reduce MPS memory pressure
4. For each prompt:
   - Run inference: pipeline(prompt, num_inference_steps=4, guidance_scale=0.0)
   - Output size: 1280×720 (landscape, for social media)
   - Save PNG to output_dir/image_{i}.png
5. Return GenerateResult(ok=True, images=[...])
```

## Key Design Decisions

- **FluxPipeline, not StableDiffusionPipeline** — FLUX.1 requires its own pipeline class
- **bfloat16 on MPS** — float16 causes black images with FLUX on Apple Silicon
- **num_inference_steps=4, guidance_scale=0.0** — FLUX.1-schnell is guidance-distilled; these are the correct settings
- **1280×720 output** — landscape format for social media use
- **No CLI** — library only; callers use the Python API directly
- **MPS only** — hardcoded `_PIPELINE.to("mps")`; CUDA not implemented
- **Global pipeline cache** — model loads once per process, subsequent calls are instant
- **No pytest/unit tests** — test by running `python test_e2e.py`

## Environment Variables

| Env var | Required | Default | Description |
|---|---|---|---|
| `HF_MODEL` | No | `black-forest-labs/FLUX.1-schnell` | Model ID |
| `HF_TOKEN` | No | — | HuggingFace token (kept for gated model support) |

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
