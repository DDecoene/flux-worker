# flux-worker — Claude Instructions

## What This Project Is

A Python package + Docker image for generating images with FLUX.1-schnell on ephemeral Vast.ai GPUs. Two components:

1. **Docker image** (`docker/`) — runs on the GPU instance, weights pre-baked in
2. **Python client** (`flux_worker/`) — orchestrates Vast.ai lifecycle, installable via pip

## Project Goals

- Simple, agent-friendly API: `generate(prompts) -> list[Path]`
- Zero runtime downloads (weights in Docker image)
- Works as a standalone tool anyone can `pip install flux-worker`
- Also used internally by `social-agent` project

## Tech Stack

- Python 3.10+, UV (never pip for dev)
- Docker (CUDA base image, weights baked in at build time)
- Vast.ai API for GPU lifecycle
- diffusers + torch for inference (inside Docker only)
- python-dotenv for .env support
- Click for CLI

## Architecture

```
flux_worker/
├── __init__.py       # public API: generate()
├── cli.py            # Click CLI entry point
├── orchestrator.py   # top-level flow: find GPU → rent → run → download → destroy
└── vastai.py         # Vast.ai API calls (find offer, create/destroy instance, SSH/SCP)

docker/
├── Dockerfile        # nvidia/cuda base + deps + model weights baked in
└── worker.py         # runs inside container: reads PROMPT env var, writes /output/image.png

.github/workflows/
└── build.yml         # builds Docker image and pushes to ghcr.io on push to main
```

## Key Design Decisions

- **Weights in Docker image**: avoids HF download at runtime. Build arg `HF_TOKEN` used at build time only.
- **SSH key**: user's local SSH key (~/.ssh/id_ed25519 or configured) must be registered in Vast.ai account. No secrets passed to instances.
- **Images downloaded via SSH**: orchestrator SSH-cats `/output/image.png` from instance to local machine. No SCP instability.
- **Always destroy**: GPU instance always destroyed in `finally` block, even on crash.
- **Batch on one instance**: if multiple prompts, generate all on the same instance before destroying.
- **No pytest/unit tests**: manual/live testing only. Test by actually running against Vast.ai.
- **Public Docker image**: `ghcr.io/ddecoene/flux-worker` is public, no auth needed on Vast.ai instances.

## Vast.ai API Notes

- Endpoint: `https://console.vast.ai/api/v0`
- Auth: `Authorization: Bearer <api_key>`
- Find offers: `GET /bundles` with query params
- Create instance: `PUT /asks/{offer_id}/` with `{"image": ..., "env": {...}, "disk": 50, "onstart": "..."}`
- `env` field = JSON dict (NOT Docker flags string)
- Instance status: `GET /instances/` returns `{"instances": [...]}`
- Destroy: `DELETE /instances/{id}/`
- SSH keys registered in Vast.ai account are auto-injected into instances
- Instance status goes: None → loading → running
- SSH may report ready but daemon needs ~30s to stabilize
- Filter on `gpu_ram gte`, `dph_total lte`, `rentable eq true`
- Prefer newer GPU architectures (RTX 3090/4090, A100) over V100 — better CUDA support and faster network

## GPU Requirements

- Min 16GB VRAM for FLUX.1-schnell with float16
- Prefer `cuda_vers gte 12.0`
- Max $0.50/hr default, configurable
- Avoid V100 — no native float16 bfloat16, slow network on cheap hosts

## Worker Interface

The Docker worker (`docker/worker.py`) reads:
- `PROMPT` env var (required) — the image prompt
- `OUTPUT_DIR` env var (optional, default `/output`) — where to save image

Writes:
- `/output/image.png` — the generated image
- `/output/done` — sentinel file with content "ok" when complete

## SSH Key

Default: `~/.ssh/id_ed25519` (fall back to `~/.ssh/id_rsa`). Configurable via `ssh_key_path` param or `SSH_KEY_PATH` env var. Must be registered in Vast.ai account settings.

## .env.example

```
VASTAI_API_KEY=
HF_TOKEN=
SSH_KEY_PATH=~/.ssh/id_ed25519
```

## Installation for Development

```bash
git clone https://github.com/ddecoene/flux-worker
cd flux-worker
uv sync
```

## GitHub Actions

The workflow builds the Docker image with model weights baked in. Requires:
- `HF_TOKEN` secret in GitHub repo settings (for downloading weights at build time)
- `GHCR_TOKEN` or uses `GITHUB_TOKEN` for pushing to ghcr.io

Image tag: `ghcr.io/ddecoene/flux-worker:latest` and `ghcr.io/ddecoene/flux-worker:sha-{commit}`
