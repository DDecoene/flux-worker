# flux-worker

Generate images with [FLUX.1-schnell](https://huggingface.co/black-forest-labs/FLUX.1-schnell) on ephemeral Vast.ai GPUs. Model weights are baked into the Docker image — no Hugging Face downloads at runtime.

## Features

- **Zero cold-start downloads** — weights pre-baked into Docker image (~30GB)
- **Simple interface** — prompt in, image file out
- **Agent-friendly Python API** — call from code or AI agents
- **CLI** — run from terminal with `.env` support
- **Batch generation** — pass multiple prompts or a JSON file
- **Cheap** — spins up GPU, generates, destroys. Pay only for what you use (~$0.05/image)

## Quick Start

```bash
pip install flux-worker
```

Set your Vast.ai key in `.env` or pass it directly:

```bash
VASTAI_API_KEY=your_key
```

### CLI

```bash
# Single prompt
flux-worker generate "a cyclist at golden hour in the Flemish polders"

# Multiple prompts
flux-worker generate "prompt one" "prompt two" "prompt three"

# From JSON file
flux-worker generate --prompts-file prompts.json

# Custom output directory
flux-worker generate "a cyclist at golden hour" --output ./my-images/

# Pass key explicitly
flux-worker generate "a cyclist" \
  --vastai-key sk_xxx

# Tune GPU selection
flux-worker generate "a cyclist" \
  --max-gpu-price 0.30 \
  --min-vram-gb 24 \
  --min-cuda-version 12.0 \
  --disk-gb 50
```

### Python API

```python
from flux_worker import generate

# Single image
paths = generate("a cyclist at golden hour in the Flemish polders")

# Batch
paths = generate([
    "a cyclist at golden hour in the Flemish polders",
    "a runner in the rain, cinematic lighting",
    "a swimmer at sunrise, aerial view",
])

# All options
paths = generate(
    prompts=["a cyclist at golden hour"],
    output_dir="./images",
    vastai_api_key="sk_xxx",        # or set VASTAI_API_KEY in .env
    max_gpu_price=0.50,             # max $/hr, default 0.50
    min_vram_gb=16,                 # default 16
    min_cuda_version=12.0,          # default 12.0
    disk_gb=50,                     # default 50
    ssh_key_path="~/.ssh/id_ed25519",
)
# returns list of Path objects
```

### prompts.json format

```json
["prompt one", "prompt two", "prompt three"]
```

## How It Works

1. Client finds cheapest available Vast.ai GPU
2. Rents instance with pre-built Docker image (`ghcr.io/ddecoene/flux-worker`)
3. Docker image runs immediately — no downloads, no setup
4. Worker generates images from prompts, saves to `/output/`
5. Client downloads images via SSH
6. GPU instance is destroyed

Total time: ~3-5 minutes for first image, ~30 seconds per additional image.

## Using the Docker Image Directly

```bash
# On any CUDA machine
docker run --gpus all \
  -e PROMPT="a cyclist at golden hour" \
  -v $(pwd)/output:/output \
  ghcr.io/ddecoene/flux-worker:latest
```

On Vast.ai, set `onstart` to:
```
docker run --gpus all -e PROMPT="your prompt" -v /output:/output ghcr.io/ddecoene/flux-worker:latest
```

## GPU Selection

The client searches Vast.ai for the cheapest available GPU that meets the requirements. All parameters have sensible defaults for FLUX.1-schnell:

| Parameter | CLI flag | Env var | Default | Notes |
|---|---|---|---|---|
| Max price | `--max-gpu-price` | `MAX_GPU_PRICE` | `0.50` | $/hr |
| Min VRAM | `--min-vram-gb` | `MIN_VRAM_GB` | `16` | GB, minimum for FLUX float16 |
| Min CUDA | `--min-cuda-version` | `MIN_CUDA_VERSION` | `12.0` | Older versions have bfloat16 issues |
| Disk | `--disk-gb` | `DISK_GB` | `50` | GB allocated to instance |
| SSH key | `--ssh-key-path` | `SSH_KEY_PATH` | `~/.ssh/id_ed25519` | Must be registered in Vast.ai account |

GPUs with less than 16GB VRAM or CUDA < 12.0 are excluded automatically. V100s are avoided — no native bfloat16 and typically slow network on cheap hosts.

## Environment Variables

| Variable | Description | Required |
|---|---|---|
| `VASTAI_API_KEY` | Vast.ai API key | Yes |
| `MAX_GPU_PRICE` | Max $/hr for GPU instance | No (default: `0.50`) |
| `MIN_VRAM_GB` | Minimum VRAM in GB | No (default: `16`) |
| `MIN_CUDA_VERSION` | Minimum CUDA version | No (default: `12.0`) |
| `DISK_GB` | Disk space allocated to instance | No (default: `50`) |
| `SSH_KEY_PATH` | Path to SSH private key | No (default: `~/.ssh/id_ed25519`) |

## Building the Docker Image

Only needed if you've forked the repo and want to build your own image. The pre-built `ghcr.io/ddecoene/flux-worker` image already has weights baked in — no Hugging Face account required to use it.

Building requires ~30GB disk space and a Hugging Face token (to download the weights at build time).

```bash
docker build \
  --build-arg HF_TOKEN=your_hf_token \
  -t flux-worker \
  docker/
```

The pre-built image at `ghcr.io/ddecoene/flux-worker` is built from this repo's `main` branch. If you want to customize the worker or host your own image, fork this repo — GitHub Actions will build and push to your own `ghcr.io/<your-username>/flux-worker` automatically.

## License

Apache-2.0
