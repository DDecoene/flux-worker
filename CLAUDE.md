# flux-worker — Claude Instructions

## What This Project Is

A Python package + Docker image for generating images with FLUX.1-schnell on ephemeral Vast.ai GPUs. Two components:

1. **Docker image** (`docker/`) — runs on the GPU instance, weights pre-baked in, exposes HTTP API
2. **Python client** (`flux_worker/`) — orchestrates Vast.ai lifecycle, installable via pip

## Project Goals

- Simple, agent-friendly API: `generate(prompts) -> list[Path]`
- Zero runtime downloads (weights in Docker image)
- Resume-on-restart: if orchestrator crashes, restart it and it reconnects to the existing GPU instance
- CLI users install via Homebrew (`brew tap ddecoene/tap && brew install flux-worker`)
- Python/agent users install via pip or pipx (`pip install flux-worker`)
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
├── orchestrator.py   # top-level flow: find/resume GPU → poll worker → generate → destroy
├── vastai.py         # Vast.ai API calls (find offer, create/destroy instance, port lookup)
├── config.py         # Config dataclass + env loading
├── result.py         # GenerateResult dataclass
├── exceptions.py     # UserError, VastAIError
└── bug_report.py     # auto-file GitHub issues on unexpected errors

docker/
├── Dockerfile        # nvidia/cuda base + deps + model weights baked in, EXPOSE 5000
└── worker.py         # HTTP server: GET /health, POST /generate

.github/workflows/
└── build.yml         # builds Docker image and pushes to ghcr.io on push to main
```

## How It Works — The Full Flow

### Normal flow (no existing instance)

```
1. orchestrator.generate(prompts) called
2. load_config() reads .env + params
3. find_resumable_instance() → None (no existing instance)
4. find_offer() → cheapest GPU meeting requirements
5. create_instance() → rents GPU, passes WORKER_TOKEN env var
   Instance starts: Vast.ai pulls Docker image (5-15 min)
6. _wait_for_worker() polls:
   - GET /instances/ → wait for actual_status == "running"
   - Extract worker URL from instance port mapping
   - GET {worker_url}/health → wait for 200 (model loading, ~60s)
   - While waiting: poll instance logs and print [gpu] lines
7. _generate_images() for each prompt:
   - POST {worker_url}/generate {prompt, index}
   - Worker generates image (~30s), returns base64 PNG in response
   - Orchestrator decodes and saves to output_dir/image_{i}.png
8. finally: destroy_instance() — always, even on crash
```

### Resume flow (orchestrator crashed and restarted)

```
1. orchestrator.generate(prompts) called
2. find_resumable_instance() → finds instance with label "flux-worker-token:{uuid}"
   Extracts token from label, reuses instance_id
3. _wait_for_worker():
   - Instance may still be loading (pulling image) → keeps polling
   - Instance may be running with model loaded → /health returns 200 immediately
   - Instance may be running, model still loading → /health times out, retry
4. Once /health returns 200 → proceed with _generate_images()
5. finally: destroy_instance()
```

**Why resume works:** The orchestrator connects TO the worker (not the other way around). The worker's IP/port is stable — it comes from the Vast.ai API. No tunnel URLs to go stale.

**Why we chose this over callbacks:** Vast.ai has no API to update env vars on a running/loading instance. A callback model requires the GPU to know the orchestrator's URL, which changes on restart (cloudflared tunnels are ephemeral). By reversing the direction, the orchestrator looks up the worker's address from Vast.ai every time.

### Instance labeling

Every instance is created with label `flux-worker-token:{uuid}`. This serves two purposes:
1. **Resume detection**: `find_resumable_instance()` looks for instances with this label prefix
2. **Auth token**: the UUID is passed as `WORKER_TOKEN` env var and used as Bearer token for all HTTP requests to the worker

## Worker Interface (docker/worker.py)

The worker is an HTTP server on port 5000 inside the container.

### Endpoints

| Endpoint | Method | Auth | Request | Response |
|---|---|---|---|---|
| `/health` | GET | Bearer token | — | `{"status": "ready"}` |
| `/generate` | POST | Bearer token | `{"prompt": "...", "index": 0}` | `{"image_b64": "...", "index": 0}` |

### Startup sequence

1. Load FLUX model into GPU memory (~60s)
2. Start HTTP server on `0.0.0.0:5000`
3. Server blocks on `serve_forever()` — handles one request at a time

**Note:** `/health` only returns 200 AFTER the model is loaded. The server doesn't start until model loading is complete. This means "healthy" = "ready to generate".

### Env vars (set at instance creation)

| Var | Required | Description |
|---|---|---|
| `WORKER_TOKEN` | Yes | Bearer token for auth |
| `WORKER_PORT` | No | HTTP port (default: 5000) |
| `OUTPUT_DIR` | No | Image save dir (default: `/output`) |

## Key Design Decisions

- **Weights in Docker image**: avoids HF download at runtime. Build arg `HF_TOKEN` used at build time only.
- **Orchestrator-polls-worker model**: orchestrator connects to worker HTTP API using IP/port from Vast.ai API. No SSH, no tunnels, no callback URLs. Enables resume because the worker's address is always discoverable.
- **Token auth via instance label**: the auth token is embedded in the instance label, so the orchestrator can recover it on resume without needing to store state locally.
- **Always destroy**: GPU instance always destroyed in `finally` block, even on crash.
- **Batch on one instance**: if multiple prompts, generate all on the same instance before destroying.
- **No pytest/unit tests**: manual/live testing only. Test by actually running against Vast.ai.
- **Public Docker image**: `ghcr.io/ddecoene/flux-worker` is public, no auth needed on Vast.ai instances.

## Vast.ai API Notes

- Endpoint: `https://console.vast.ai/api/v0`
- Auth: `Authorization: Bearer <api_key>`
- Find offers: `GET /bundles` with query params
- Create instance: `PUT /asks/{offer_id}/` with `{"image": ..., "env": {...}, "disk": 50, "label": "..."}`
- `env` field = JSON dict (NOT Docker flags string)
- Instance status: `GET /instances/` returns `{"instances": [...]}`
- Instance logs: `GET /instances/{id}/logs` returns `{"logs": "..."}`
- Reboot (stop+start container): `PUT /instances/reboot/{id}/`
- Destroy: `DELETE /instances/{id}/`
- Instance status goes: creating → loading → running
- **Cannot update env vars** on an existing instance — env is set at creation time only
- **Port exposure**: Dockerfile `EXPOSE 5000` tells Vast.ai to map the port. Instance info contains port mappings in `ports` field and/or `public_ipaddr` for direct access.
- Filter on `gpu_ram gte`, `dph_total lte`, `rentable eq true`
- Prefer newer GPU architectures (RTX 3090/4090, A100) over V100 — better CUDA support and faster network

## Vast.ai Port Mapping (needs e2e verification)

The `get_worker_url()` function extracts the worker's HTTP URL from instance info. Two approaches tried in order:

1. **Port mapping dict**: `inst["ports"]["5000/tcp"][0]["HostPort"]` + `inst["public_ipaddr"]`
2. **Direct port fallback**: `inst["direct_port_start"]` + `inst["public_ipaddr"]`

The exact field format needs verification against a real instance response. During the e2e test, inspect the full instance dict to confirm which fields are populated.

## GPU Requirements

All configurable with sensible defaults:

| Parameter | Default | Env var | Notes |
|---|---|---|---|
| Max price | `0.50` $/hr | `MAX_GPU_PRICE` | |
| Min VRAM | `16` GB | `MIN_VRAM_GB` | Minimum for FLUX float16 |
| Min CUDA | `12.0` | `MIN_CUDA_VERSION` | Older versions lack bfloat16 |
| Disk | `50` GB | `DISK_GB` | |

- Avoid V100 — no native bfloat16, slow network on cheap hosts

## .env.example

```
VASTAI_API_KEY=
MAX_GPU_PRICE=0.50
MIN_VRAM_GB=16
MIN_CUDA_VERSION=12.0
DISK_GB=50
```

`HF_TOKEN` is only needed when building the Docker image (bakes weights at build time). Not required at runtime.

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
