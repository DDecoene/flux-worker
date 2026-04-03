# flux-worker — Claude Instructions

## What This Project Is

A Python package for local image generation using `diffusers` and PyTorch. Defaults to Stable Diffusion 2.1. Zero cost, runs entirely on your GPU.

- **Python client** (`flux_worker/`) — local inference with diffusers, saves images locally, installable via pip
- No cloud API calls, no tokens required (optional for gated models)
- Supports macOS (Apple Silicon) and Linux/Windows (NVIDIA GPU)

## Project Goals

- Simple, agent-friendly API: `generate(prompts) -> GenerateResult`
- Zero cloud dependency or costs
- Fast inference on local hardware (~3-5s per image on M2)
- CLI users install via Homebrew (`brew tap ddecoene/tap && brew install flux-worker`)
- Python/agent users install via pip or pipx
- Also used internally by `social-agent` project

## Tech Stack

- Python 3.10+, UV (never pip for dev)
- `diffusers` library for model inference
- `torch` for GPU computation (runs on MPS for Apple Silicon, CUDA for NVIDIA)
- Click for CLI
- python-dotenv for .env support

## Architecture

```
flux_worker/
├── __init__.py       # public API: generate()
├── cli.py            # Click CLI entry point
├── orchestrator.py   # loads diffusers pipeline, runs inference, saves images
├── config.py         # Config dataclass + env loading
├── result.py         # GenerateResult dataclass
├── exceptions.py     # UserError, FluxError
└── bug_report.py     # auto-file GitHub issues on unexpected errors
```

## How It Works

```
1. generate(prompts) called
2. load_config() reads HF_MODEL from env (default: stabilityai/stable-diffusion-2-1)
3. First call only:
   - Download model from HuggingFace Hub (~2.5GB, cached locally)
   - Load into GPU memory (float16 quantization for efficiency)
4. For each prompt:
   - Run inference: pipeline(prompt, num_inference_steps=20)
   - Receives PIL.Image object
   - Save PNG to output_dir/image_{i}.png
5. Return GenerateResult(ok=True, images=[...])
```

## Model Support

Tested & working:
- `stabilityai/stable-diffusion-2-1` (3.5GB, fast, ~3-5s, default)
- `stabilityai/stable-diffusion-xl-base-1.0` (6GB, better quality, ~8-10s)

With quantization (8GB M2):
- `black-forest-labs/FLUX.1-schnell` (requires int8 quantization)

## Key Design Decisions

- **Local inference only**: No cloud API, no tokens (except optional for gated models)
- **Float16 quantization**: Reduces model size, fits on 8GB M2/GPU VRAM
- **Safety checker disabled**: Removes overhead, assumes responsible use
- **Global pipeline cache**: Model loads once per process, subsequent calls are instant
- **MPS-optimized for Apple Silicon**: Uses Metal Performance Shaders for native GPU support
- **No pytest/unit tests**: Manual/live testing only. Test by actually running `flux-worker generate "test"`

## .env.example

```
# Optional: which model to use
# HF_MODEL=stabilityai/stable-diffusion-2-1

# Optional: HF token for gated models
# HF_TOKEN=hf_...
```

## Environment Variables

| Env var | Required | Default | Description |
|---|---|---|---|
| `HF_MODEL` | No | `stabilityai/stable-diffusion-2-1` | Model ID from huggingface.co |
| `HF_TOKEN` | No | — | HuggingFace token (only needed for gated models) |

## Installation for Development

```bash
git clone https://github.com/ddecoene/flux-worker
cd flux-worker
uv sync
```

## Testing

Run against the real HuggingFace API:

```bash
export HF_TOKEN=hf_...
flux-worker generate "a red panda on a surfboard"
# Expect: output/image_0.png written in ~10-30s
```
