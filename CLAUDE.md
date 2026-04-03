# flux-worker — Claude Instructions

## What This Project Is

A Python package for generating images via the HuggingFace Inference API. Defaults to Stable Diffusion XL (`stabilityai/stable-diffusion-xl-base-1.0`).

- **Python client** (`flux_worker/`) — calls HF Inference API, saves images locally, installable via pip
- No Docker, no GPU management, no cloud instance lifecycle

## Project Goals

- Simple, agent-friendly API: `generate(prompts) -> GenerateResult`
- CLI users install via Homebrew (`brew tap ddecoene/tap && brew install flux-worker`)
- Python/agent users install via pip or pipx (`pip install flux-worker`)
- Also used internally by `social-agent` project

## Tech Stack

- Python 3.10+, UV (never pip for dev)
- HuggingFace Inference API (HTTP)
- python-dotenv for .env support
- Click for CLI
- requests for HTTP

## Architecture

```
flux_worker/
├── __init__.py       # public API: generate()
├── cli.py            # Click CLI entry point
├── orchestrator.py   # calls HF Inference API, saves images
├── config.py         # Config dataclass + env loading
├── result.py         # GenerateResult dataclass
├── exceptions.py     # UserError, FluxError
└── bug_report.py     # auto-file GitHub issues on unexpected errors
```

## How It Works

```
1. generate(prompts) called
2. load_config() reads HF_TOKEN from .env / env vars
3. For each prompt:
   - POST https://api-inference.huggingface.co/models/{model}
     body: {"inputs": "<prompt>"}
     auth: Authorization: Bearer <HF_TOKEN>
   - On 503 (model loading): wait estimated_time seconds, retry (up to 5 min)
   - On 200: write raw PNG bytes to output_dir/image_{i}.png
4. Return GenerateResult(ok=True, images=[...])
```

## HuggingFace Inference API Notes

- Base URL: `https://api-inference.huggingface.co/models`
- Auth: `Authorization: Bearer <HF_TOKEN>`
- Request: `POST /{model_id}` with body `{"inputs": "prompt text"}`
- Response on success: raw PNG bytes (Content-Type: image/png)
- Response on model loading: HTTP 503, body `{"error": "...", "estimated_time": N}`
- Response on bad token: HTTP 401
- Free tier is rate-limited; paid inference API is faster and more reliable

## Key Design Decisions

- **No local inference**: all generation happens in HuggingFace cloud. No GPU, no Docker, no torch.
- **503 retry loop**: HF cold-starts models; orchestrator retries up to `MODEL_LOAD_MAX_WAIT` seconds.
- **No pytest/unit tests**: manual/live testing only. Test by actually running against the HF API.

## .env.example

```
HF_TOKEN=
# HF_MODEL=stabilityai/stable-diffusion-xl-base-1.0
```

## Config

| Env var | Required | Default | Description |
|---|---|---|---|
| `HF_TOKEN` | Yes | — | HuggingFace API token |
| `HF_MODEL` | No | `stabilityai/stable-diffusion-xl-base-1.0` | Model ID |

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
