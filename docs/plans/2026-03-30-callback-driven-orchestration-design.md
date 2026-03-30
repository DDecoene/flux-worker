# Callback-Driven Orchestration Design

**Date:** 2026-03-30
**Status:** Approved

## Problem

The current SSH polling approach is fragile:
- Orchestrator crash leaves GPU instance running with no way to resume
- No visibility into what the GPU is doing
- SSH readiness polling is unreliable
- Multiple prompts require staying connected over SSH for the full duration

## Design

Replace SSH polling with an HTTP callback protocol. The orchestrator exposes a local HTTP server tunneled via cloudflared. The GPU instance calls back to signal readiness and report results. Prompts are delivered via callback responses rather than env vars.

## Startup & Resume Logic

On every run, before creating a new instance:

1. Query Vast.ai for instances with image `ghcr.io/ddecoene/flux-worker:latest`
2. Look for instance label matching `flux-worker-token:<uuid>`
3. If found and status is `running` or `loading`: extract token, start HTTP server + cloudflared tunnel with that token, wait for GPU's next retry
4. If not found: generate new token, create new instance

This eliminates local state files. The Vast.ai instance itself is the source of truth.

## Instance Creation

Env vars passed to GPU at creation:
```
CALLBACK_URL=https://xxx.trycloudflare.com
CALLBACK_TOKEN=<uuid4>
```

Prompts are **not** in env vars. They are delivered in the response to `/ready`.

Instance label set at creation: `flux-worker-token:<uuid4>`

## Callback Protocol

### GPU → `/ready`
```json
POST /ready
{"token": "<uuid>"}
```
Response:
```json
{"prompt": "a red cat on a cloud", "index": 0}
```

GPU retries this every 5 minutes, up to 5 attempts (25 min window), before exiting.

### GPU → `/done`
```json
POST /done
{"token": "<uuid>", "index": 0, "image_b64": "<base64 PNG>"}
```
Response (more work):
```json
{"prompt": "next prompt", "index": 1}
```
Response (no more work):
```json
{"done": true}
```
GPU exits cleanly on `{"done": true}`.

## Orchestrator Flow

```
start HTTP server (random port)
start cloudflared tunnel → get public URL
check Vast.ai for resumable instance
  → found: extract token, wait for /ready retry
  → not found: create new instance with token + label

wait for POST /ready (timeout: 30 min)
  → while waiting: poll Vast.ai logs every 30s, print to stdout

on /ready: respond with first prompt

wait for POST /done (timeout: 10 min per image)
  → while waiting: poll logs every 30s

on /done: save image, send next prompt or {"done": true}

finally: destroy instance, shut down cloudflared, stop HTTP server
```

## Timeouts

| Event | Timeout |
|---|---|
| First `/ready` | 30 minutes |
| Per-image `/done` | 10 minutes |
| GPU `/ready` retry interval | 5 minutes |
| GPU `/ready` max attempts | 5 |

## Log Polling

While waiting for any callback, the orchestrator polls `GET /instances/{id}/logs` every 30 seconds and prints new lines to stdout. This gives visibility into image pull progress, worker startup, and errors.

## cloudflared

- On startup, check if `cloudflared` is in PATH
- If not: print install instructions (`brew install cloudflare/cloudflare/cloudflared`) and exit with clear error
- Start as subprocess: `cloudflared tunnel --url http://localhost:<port>`
- Parse tunnel URL from subprocess stdout
- Terminate subprocess in `finally`

## Files Changed

| File | Change |
|---|---|
| `orchestrator.py` | Rewritten around callback flow |
| `docker/worker.py` | Replace sentinel/SSH with HTTP callbacks |
| `flux_worker/callback_server.py` | New — tiny HTTP server (stdlib `http.server`) |
| `flux_worker/tunnel.py` | New — manages cloudflared subprocess |
| `flux_worker/vastai.py` | Add label to `create_instance`; add `get_instance_logs`; add label-based instance lookup |

## What Is Removed

- All SSH usage (`paramiko`, `wait_for_ssh`, `file_exists_ssh`, `read_file_ssh`, `download_file_ssh`)
- Sentinel file polling (`done_N` files)
- `PROMPTS` env var on GPU
- `paramiko` dependency
