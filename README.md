# flux-worker

Generate images locally on your machine. Uses [diffusers](https://github.com/huggingface/diffusers) library with [Stable Diffusion 2.1](https://huggingface.co/stabilityai/stable-diffusion-2-1) by default.

- **Simple interface** — prompt in, image file out
- **Local inference** — runs entirely on your GPU, no API calls
- **Free** — no tokens, no cloud bills
- **Fast** — ~3-5 seconds per image on Apple Silicon or modern GPU
- **Batch generation** — pass multiple prompts, images saved locally

## Requirements

- **macOS (Apple Silicon)**: M1/M2/M3 or newer, 8GB+ RAM
- **Linux/Windows**: NVIDIA GPU with 8GB+ VRAM (CUDA 11.8+)
- **Storage**: ~2-4GB for model weights (one-time download)

## Installation

### CLI tool — Homebrew (macOS)

```bash
brew tap ddecoene/tap
brew install flux-worker
```

### Python library — pip or pipx

```bash
# pipx: isolated install + CLI
pipx install flux-worker

# pip: install into your project
pip install flux-worker
```

### First run

First time you generate an image, the model (~2.5GB) will download automatically from HuggingFace.

```bash
flux-worker generate "a cyclist at golden hour"
# First run: downloading model (1-2 min)
# Generating image 1/1: a cyclist at golden hour...
# Saved: ./output/image_0.png
```

On subsequent runs, the model is cached — no download needed.

### Claude Code agent tool

Add to your `CLAUDE.md`:

```
You have access to flux-worker for generating images.
Use the bash tool to run: flux-worker generate "<prompt>"
Images are saved to ./output/ by default.
```

Or call directly from Python:

```python
from flux_worker import generate

result = generate("a cyclist at golden hour")
print(result.images[0])  # Path to PNG
```

## Usage

### CLI

```bash
# Single prompt
flux-worker generate "a cyclist at golden hour in the Flemish polders"

# Multiple prompts
flux-worker generate "a cyclist" "a runner" "a swimmer"

# From JSON file
flux-worker generate --prompts-file prompts.json

# Custom output directory
flux-worker generate "a cyclist" --output ./my-images/

# Use a different model
flux-worker generate "a cyclist" --model stabilityai/stable-diffusion-xl-base-1.0
```

### Python API

```python
from flux_worker import generate

# Single image
result = generate("a cyclist at golden hour in the Flemish polders")
if result.ok:
    print(result.images[0])  # Path to saved PNG

# Batch
result = generate([
    "a cyclist at golden hour in the Flemish polders",
    "a runner in the rain, cinematic lighting",
    "a swimmer at sunrise, aerial view",
])

# With custom settings
result = generate(
    prompts=["a cyclist"],
    output_dir="./images",
    model="stabilityai/stable-diffusion-xl-base-1.0",
)

# Check results
print(f"Success: {result.ok}")
print(f"Images: {result.images}")
```

### prompts.json format

```json
["prompt one", "prompt two", "prompt three"]
```

## Environment Variables

Optional. Place in a `.env` file or export in your shell:

| Variable | Description | Default |
|---|---|---|
| `HF_MODEL` | Model ID from huggingface.co | `stabilityai/stable-diffusion-2-1` |
| `HF_TOKEN` | HuggingFace token (for gated models) | — |

### Recommended models

- **Fast (~3-5s)**: `stabilityai/stable-diffusion-2-1` (default, 3.5GB)
- **Better quality (~8-10s)**: `stabilityai/stable-diffusion-xl-base-1.0` (6GB, requires more VRAM)
- **Experimental**: `black-forest-labs/FLUX.1-schnell` (requires quantization on M2)

## License

Apache-2.0
