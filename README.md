# flux-worker

Generate images locally on your machine. Uses [diffusers](https://github.com/huggingface/diffusers) library with [Stable Diffusion v1.5](https://huggingface.co/runwayml/stable-diffusion-v1-5) by default.

- **Simple interface** — prompt in, image file out
- **Local inference** — runs entirely on your GPU, no API calls
- **Free** — no tokens required (HF_TOKEN optional for gated models)
- **Fast** — ~5-10 seconds per image on Apple Silicon
- **Batch generation** — pass multiple prompts, images saved locally

> **Platform support**: Currently optimized for **macOS Apple Silicon** (MPS). Linux/NVIDIA CUDA support is not yet implemented.

## Requirements

- **macOS (Apple Silicon)**: M1/M2/M3 or newer, 8GB+ RAM
- **Storage**: ~2.5GB for model weights (one-time download, cached by HuggingFace)

## Installation

### CLI tool — Homebrew (macOS)

```bash
brew tap ddecoene/tap
brew install flux-worker
```

### Python library — from GitHub

Not yet published to PyPI. Install directly from GitHub:

```bash
# uv (recommended)
uv add "flux-worker @ git+https://github.com/DDecoene/flux-worker.git"

# pip
pip install "flux-worker @ git+https://github.com/DDecoene/flux-worker.git"

# pipx (installs CLI into isolated env)
pipx install "flux-worker @ git+https://github.com/DDecoene/flux-worker.git"
```

### First run

First time you generate an image, the model (~2.5GB) will download automatically from HuggingFace and be cached locally.

```bash
flux-worker generate "a cyclist at golden hour"
# First run: downloading model (~1-2 min, one-time)
# Generating image 1/1: a cyclist at golden hour...
# Saved: ./output/image_0.png
```

Subsequent calls are fast — model is cached in `~/.cache/huggingface/`.

### Using in your Python project

```bash
uv add "flux-worker @ git+https://github.com/DDecoene/flux-worker.git"
```

```python
from flux_worker import generate

result = generate("a cyclist at golden hour")
if result.ok:
    print(result.images[0])  # Path to saved PNG
else:
    print(result.error_message)
```

### Using with Claude Code or other AI coding agents

Add to your project's `CLAUDE.md`:

```markdown
## Image generation

This project uses flux-worker for local image generation.

- CLI: `flux-worker generate "<prompt>"` — images saved to `./output/`
- Python: `from flux_worker import generate; result = generate("<prompt>")`
- Result object: `result.ok` (bool), `result.images` (list of Path), `result.error_message` (str)
- No API keys needed for the default model
- First run downloads ~2.5GB model, subsequent runs are instant
```

The agent can then call the CLI via Bash or import the Python API directly.

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
| `HF_MODEL` | Model ID from huggingface.co | `runwayml/stable-diffusion-v1-5` |
| `HF_TOKEN` | HuggingFace token (for gated models) | — |

### Recommended models

- **Fast (~5-10s)**: `runwayml/stable-diffusion-v1-5` (default, ~2.5GB) — public, requires no authentication
- **Better quality (~10-20s)**: `stabilityai/stable-diffusion-xl-base-1.0` (6GB, requires HF_TOKEN for gated access)
- **Experimental**: `black-forest-labs/FLUX.1-schnell` (requires quantization on M2 and HF_TOKEN)

## License

Apache-2.0
