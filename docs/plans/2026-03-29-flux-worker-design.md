# flux-worker Design

## Overview

A Python package that generates images with FLUX.1-schnell on ephemeral Vast.ai GPUs. Python API is the primary interface; CLI is a thin wrapper around it.

## Architecture

```
flux-worker/
├── flux_worker/
│   ├── __init__.py       # generate() — public API
│   ├── cli.py            # Click CLI, wraps generate()
│   ├── orchestrator.py   # top-level flow: validate → find GPU → rent → run → poll/download → destroy
│   └── vastai.py         # Vast.ai REST API calls + SSH operations
├── docker/
│   ├── Dockerfile        # nvidia/cuda base, weights baked in at build time
│   └── worker.py         # runs on GPU instance, reads PROMPTS env var, writes images + sentinels
├── .github/workflows/
│   └── build.yml         # builds + pushes Docker image on push to main
└── pyproject.toml        # package metadata, CLI entry point
```

`docker/` is built once and published to `ghcr.io/ddecoene/flux-worker`. The Python package never imports from it.

## Public API

```python
from flux_worker import generate

paths = generate(
    prompts,                          # str or list[str]
    output_dir="./output",
    vastai_api_key=None,              # falls back to VASTAI_API_KEY env var
    max_gpu_price=0.50,
    min_vram_gb=16,
    min_cuda_version=12.0,
    disk_gb=50,
    ssh_key_path="~/.ssh/id_ed25519",
)
# returns list[Path]
```

## Data Flow

1. `generate()` validates SSH key exists (fail fast with clear error if not), loads config from env/.env
2. Finds cheapest Vast.ai GPU matching requirements via `GET /bundles`
3. Rents instance with `ghcr.io/ddecoene/flux-worker`, passes all prompts as `PROMPTS` env var (JSON array)
4. Worker generates images sequentially, writes `image_0.png` ... `image_N.png` and `done_0` ... `done_N` sentinels to `/output/`
5. Orchestrator polls via SSH every few seconds — downloads each `image_N.png` as soon as `done_N` appears, yields `Path` to caller progressively
6. Once all images downloaded, destroys instance
7. Returns `list[Path]`

Instance is always destroyed in a `finally` block, even on crash.

## Dependencies (Python package)

```toml
[project]
name = "flux-worker"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "click",
    "python-dotenv",
    "requests",
    "paramiko",
]

[project.scripts]
flux-worker = "flux_worker.cli:cli"
```

`diffusers` and `torch` live inside Docker only — the client is lightweight.

## Error Handling

Clear errors for:
- SSH key not found (`~/.ssh/id_ed25519` and `~/.ssh/id_rsa` both missing)
- No GPU available under price/VRAM/CUDA constraints
- SSH connection failure
- Worker error (non-"ok" sentinel content)

## Worker Interface

Environment variables read by `docker/worker.py`:
- `PROMPTS` — JSON array of prompt strings (required)
- `OUTPUT_DIR` — output directory (optional, default `/output`)

Files written per prompt index N:
- `/output/image_N.png` — generated image
- `/output/done_N` — sentinel, content "ok" on success or error message on failure

## GPU Selection Defaults

| Parameter | Default | Env var |
|---|---|---|
| Max price | `0.50` $/hr | `MAX_GPU_PRICE` |
| Min VRAM | `16` GB | `MIN_VRAM_GB` |
| Min CUDA | `12.0` | `MIN_CUDA_VERSION` |
| Disk | `50` GB | `DISK_GB` |
| SSH key | `~/.ssh/id_ed25519` | `SSH_KEY_PATH` |

V100s excluded — no native bfloat16, slow network on cheap hosts.

## Testing

Manual/live testing only — run against real Vast.ai. No mocks, no pytest.
