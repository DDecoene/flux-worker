# flux-worker

Generate images with [FLUX.1-schnell](https://huggingface.co/black-forest-labs/FLUX.1-schnell) on ephemeral Vast.ai GPUs. Model weights are baked into the Docker image — no Hugging Face downloads at runtime.

- **Zero cold-start downloads** — weights pre-baked into Docker image (~30GB)
- **Simple interface** — prompt in, image file out
- **Batch generation** — pass multiple prompts, all run on the same GPU before it's destroyed
- **Cheap** — spins up GPU, generates, destroys. Pay only for what you use (~$0.05/image)

## Prerequisites

Before any install method will work, you need:

1. **A Vast.ai account** — [console.vast.ai](https://console.vast.ai)
2. **A Vast.ai API key** — found in Account settings
3. **Your SSH public key registered in Vast.ai** — Account → SSH Keys. This is how the client connects to the GPU instance. Your local `~/.ssh/id_ed25519` (or `id_rsa`) must be listed there.

## Installation

Choose based on how you want to use it:

### CLI tool — use Homebrew (macOS)

If you just want to run `flux-worker` from the terminal:

```bash
brew install ddecoene/tap/flux-worker
```

No Python setup required. Then add your key:

```bash
export VASTAI_API_KEY=your_key
# or put it in ~/.config/flux-worker/.env
```

### Python library or agentic use — use pip or pipx

If you're calling `flux-worker` from Python code, an AI agent, or want to use it as a library:

```bash
# pipx: isolated install, still gives you the CLI too
pipx install flux-worker

# pip: install into your project's environment
pip install flux-worker
```

**Use this if:**
- You're building an agent that generates images (e.g. with Claude, LangChain, etc.)
- You're calling `from flux_worker import generate` in Python
- You're integrating it into a larger pipeline

### Claude Code agent tool

To give Claude access to flux-worker, add it to your `CLAUDE.md` or system prompt:

```
You have access to flux-worker for generating images.
Use the bash tool to run: flux-worker generate "<prompt>"
Images are saved to ./output/ by default.
```

Or call it directly from Python in a tool definition:

```python
from flux_worker import generate

def generate_image(prompt: str) -> str:
    paths = generate(prompt)
    return str(paths[0])
```

## Usage

### CLI

```bash
# Single prompt
flux-worker generate "a cyclist at golden hour in the Flemish polders"

# Multiple prompts (all generated on one GPU instance)
flux-worker generate "prompt one" "prompt two" "prompt three"

# From JSON file
flux-worker generate --prompts-file prompts.json

# Custom output directory
flux-worker generate "a cyclist at golden hour" --output ./my-images/

# Tune GPU selection
flux-worker generate "a cyclist" \
  --max-gpu-price 0.30 \
  --min-vram-gb 24
```

### Python API

```python
from flux_worker import generate

# Single image
paths = generate("a cyclist at golden hour in the Flemish polders")

# Batch — all on one GPU instance
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

1. Client finds cheapest available Vast.ai GPU matching your requirements
2. Rents instance with pre-built Docker image (`ghcr.io/ddecoene/flux-worker`)
3. Docker image runs immediately — no downloads, no setup
4. Worker generates images from prompts, saves to `/output/`
5. Client downloads images via SSH
6. GPU instance is destroyed

Total time: ~3-5 minutes for first image, ~30 seconds per additional image.

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

Place these in a `.env` file in your working directory, or export them in your shell.

| Variable | Description | Required |
|---|---|---|
| `VASTAI_API_KEY` | Vast.ai API key | Yes |
| `MAX_GPU_PRICE` | Max $/hr for GPU instance | No (default: `0.50`) |
| `MIN_VRAM_GB` | Minimum VRAM in GB | No (default: `16`) |
| `MIN_CUDA_VERSION` | Minimum CUDA version | No (default: `12.0`) |
| `DISK_GB` | Disk space allocated to instance | No (default: `50`) |
| `SSH_KEY_PATH` | Path to SSH private key | No (default: `~/.ssh/id_ed25519`) |

## Using the Docker Image Directly

```bash
# On any CUDA machine
docker run --gpus all \
  -e PROMPT="a cyclist at golden hour" \
  -v $(pwd)/output:/output \
  ghcr.io/ddecoene/flux-worker:latest
```

## Building Your Own Image

Only needed if you've forked the repo and want to customize the worker. The pre-built `ghcr.io/ddecoene/flux-worker` already has weights baked in — no Hugging Face account required to use it.

Fork this repo — GitHub Actions will build and push to your own `ghcr.io/<your-username>/flux-worker` automatically on every push to `main`.

To build locally (requires ~30GB disk and a Hugging Face token):

```bash
docker build \
  --build-arg HF_TOKEN=your_hf_token \
  -t flux-worker \
  docker/
```

## License

Apache-2.0
