# Callback-Driven Orchestration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace SSH polling with an HTTP callback protocol so the GPU instance calls back to the orchestrator, enabling resume-on-restart and real-time visibility.

**Architecture:** The orchestrator runs a local HTTP server exposed via a cloudflared tunnel. The GPU calls `/ready` on startup and `/done` after each image. Prompts are delivered in callback responses. On restart, the orchestrator finds any existing instance via its Vast.ai label and resumes waiting.

**Tech Stack:** Python stdlib `http.server` (no new deps), cloudflared (external binary), requests, click, diffusers+torch (GPU side).

**Note on testing:** This project has no pytest suite — testing is done by running against real Vast.ai. Each task includes a manual verification step.

---

### Task 1: tunnel.py — cloudflared subprocess manager

**Files:**
- Create: `flux_worker/tunnel.py`

**What it does:** Checks for `cloudflared` in PATH, starts `cloudflared tunnel --url http://localhost:<port>` as a subprocess, parses the public HTTPS URL from stdout, exposes `start(port) -> url` and `stop()`.

**Step 1: Create `flux_worker/tunnel.py`**

```python
import re
import subprocess
import threading
import shutil
from flux_worker.exceptions import UserError

INSTALL_MSG = (
    "cloudflared is required but not installed.\n"
    "  macOS:  brew install cloudflare/cloudflare/cloudflared\n"
    "  Linux:  https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/\n"
    "  Then re-run flux-worker."
)

class Tunnel:
    def __init__(self):
        self._proc = None
        self.url = None

    def start(self, port: int) -> str:
        if not shutil.which("cloudflared"):
            raise UserError(INSTALL_MSG)

        self._proc = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", f"http://localhost:{port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # Parse URL from output (appears within ~5s)
        url = None
        for line in self._proc.stdout:
            match = re.search(r"https://[a-z0-9\-]+\.trycloudflare\.com", line)
            if match:
                url = match.group(0)
                break

        if not url:
            self._proc.terminate()
            raise RuntimeError("cloudflared did not produce a tunnel URL")

        self.url = url
        # Drain remaining stdout in background so pipe doesn't block
        threading.Thread(target=self._proc.stdout.read, daemon=True).start()
        return url

    def stop(self):
        if self._proc:
            self._proc.terminate()
            self._proc = None
```

**Step 2: Verify manually**

```bash
uv run python -c "
from flux_worker.tunnel import Tunnel
t = Tunnel()
url = t.start(8765)
print('Tunnel URL:', url)
t.stop()
print('Stopped.')
"
```
Expected: prints a `https://xxxx.trycloudflare.com` URL then `Stopped.`

**Step 3: Commit**

```bash
git add flux_worker/tunnel.py
git commit -m "feat: cloudflared tunnel manager"
```

---

### Task 2: callback_server.py — HTTP callback server

**Files:**
- Create: `flux_worker/callback_server.py`

**What it does:** Runs a tiny HTTP server in a background thread. Receives `POST /ready` and `POST /done`. Uses a `queue.Queue` to hand events to the orchestrator thread. Validates the token on every request.

**Step 1: Create `flux_worker/callback_server.py`**

```python
import base64
import json
import queue
import random
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class CallbackServer:
    def __init__(self, token: str):
        self.token = token
        self.events = queue.Queue()
        self._server = None
        self._thread = None
        self.port = None

    def start(self) -> int:
        """Start server on a random free port. Returns port number."""
        self._server = HTTPServer(("127.0.0.1", 0), self._make_handler())
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self.port

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server = None

    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # suppress default request logs

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length)) if length else {}

                if body.get("token") != server.token:
                    self._respond(403, {"error": "invalid token"})
                    return

                if self.path == "/ready":
                    server.events.put({"type": "ready"})
                    # Response will be sent by orchestrator via response_queue
                    resp = server._wait_for_response()
                    self._respond(200, resp)

                elif self.path == "/done":
                    image_b64 = body.get("image_b64", "")
                    index = body.get("index", 0)
                    image_bytes = base64.b64decode(image_b64) if image_b64 else None
                    server.events.put({"type": "done", "index": index, "image_bytes": image_bytes})
                    resp = server._wait_for_response()
                    self._respond(200, resp)

                else:
                    self._respond(404, {"error": "not found"})

            def _respond(self, status, data):
                body = json.dumps(data).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)

        return Handler

    def send_response(self, data: dict):
        """Called by orchestrator to respond to the GPU's waiting HTTP request."""
        self._response_queue.put(data)

    def _wait_for_response(self) -> dict:
        return self._response_queue.get()

    def __init__(self, token: str):
        self.token = token
        self.events = queue.Queue()
        self._response_queue = queue.Queue()
        self._server = None
        self._thread = None
        self.port = None
```

Note: the `__init__` is defined twice above — fix by merging into one. The correct final version:

```python
import base64
import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class CallbackServer:
    def __init__(self, token: str):
        self.token = token
        self.events = queue.Queue()
        self._response_queue = queue.Queue()
        self._server = None
        self._thread = None
        self.port = None

    def start(self) -> int:
        self._server = HTTPServer(("127.0.0.1", 0), self._make_handler())
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self.port

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server = None

    def send_response(self, data: dict):
        self._response_queue.put(data)

    def _wait_for_response(self) -> dict:
        return self._response_queue.get()

    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length)) if length else {}

                if body.get("token") != server.token:
                    self._respond(403, {"error": "invalid token"})
                    return

                if self.path == "/ready":
                    server.events.put({"type": "ready"})
                    resp = server._wait_for_response()
                    self._respond(200, resp)

                elif self.path == "/done":
                    image_bytes = base64.b64decode(body["image_b64"]) if body.get("image_b64") else None
                    server.events.put({"type": "done", "index": body.get("index", 0), "image_bytes": image_bytes})
                    resp = server._wait_for_response()
                    self._respond(200, resp)

                else:
                    self._respond(404, {"error": "not found"})

            def _respond(self, status, data):
                body = json.dumps(data).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)

        return Handler
```

**Step 2: Verify manually**

```bash
uv run python -c "
import requests, threading, time
from flux_worker.callback_server import CallbackServer

TOKEN = 'test-token-123'
srv = CallbackServer(TOKEN)
port = srv.start()
print(f'Server on port {port}')

# Simulate GPU calling /ready in a thread
def fake_gpu():
    time.sleep(0.2)
    r = requests.post(f'http://127.0.0.1:{port}/ready', json={'token': TOKEN})
    print('GPU got response:', r.json())

threading.Thread(target=fake_gpu).start()

# Orchestrator receives event and sends response
evt = srv.events.get(timeout=3)
print('Orchestrator got event:', evt['type'])
srv.send_response({'prompt': 'a red cat', 'index': 0})
time.sleep(0.3)
srv.stop()
print('Done.')
"
```
Expected: `GPU got response: {'prompt': 'a red cat', 'index': 0}`

**Step 3: Commit**

```bash
git add flux_worker/callback_server.py
git commit -m "feat: HTTP callback server"
```

---

### Task 3: vastai.py — add label support, log fetching, instance resume lookup

**Files:**
- Modify: `flux_worker/vastai.py`

**Step 1: Add `label` param to `create_instance`**

In `create_instance`, add `label: str = ""` parameter and include it in the payload:

```python
def create_instance(api_key: str, offer_id: int, prompts: list, disk_gb: int, label: str = "") -> dict:
    payload = {
        "client_id": "me",
        "image": DOCKER_IMAGE,
        "disk": disk_gb,
        "env": {},  # prompts no longer passed here
        "label": label,
    }
    ...
```

Note: `prompts` param stays in signature for now but is unused — remove it and update the caller in orchestrator in Task 5.

**Step 2: Add `get_instance_logs`**

```python
def get_instance_logs(api_key: str, instance_id: int) -> str:
    """Fetch instance logs. Returns log text or empty string."""
    resp = requests.get(
        f"{VASTAI_API}/instances/{instance_id}/logs",
        headers=_headers(api_key),
    )
    try:
        _raise_for_status(resp)
        return resp.json().get("logs") or ""
    except Exception:
        return ""
```

**Step 3: Add `find_resumable_instance`**

```python
def find_resumable_instance(api_key: str) -> dict | None:
    """Find a running/loading flux-worker instance with a token label. Returns instance or None."""
    resp = requests.get(f"{VASTAI_API}/instances/", headers=_headers(api_key))
    _raise_for_status(resp)
    for inst in resp.json().get("instances", []):
        label = inst.get("label") or ""
        if (
            inst.get("image_uuid") == DOCKER_IMAGE
            and label.startswith("flux-worker-token:")
            and inst.get("actual_status") in ("running", "loading")
        ):
            return inst
    return None
```

**Step 4: Remove all SSH functions**

Delete these functions entirely:
- `_ssh_client`
- `wait_for_ssh`
- `file_exists_ssh`
- `download_file_ssh`
- `read_file_ssh`

Also remove `import paramiko` at the top.

**Step 5: Remove paramiko from pyproject.toml**

In `pyproject.toml`, remove `"paramiko>=3.0"` from dependencies.

```bash
# After editing pyproject.toml:
uv sync
```

**Step 6: Verify**

```bash
uv run python -c "
from flux_worker import vastai
import os
from dotenv import load_dotenv
load_dotenv()
inst = vastai.find_resumable_instance(os.environ['VASTAI_API_KEY'])
print('Resumable instance:', inst)
"
```
Expected: `Resumable instance: None` (no instances running)

**Step 7: Commit**

```bash
git add flux_worker/vastai.py pyproject.toml
git commit -m "feat: vastai label support, log fetching, resume lookup; drop SSH"
```

---

### Task 4: docker/worker.py — replace sentinels with HTTP callbacks

**Files:**
- Modify: `docker/worker.py`

**What changes:** Remove all sentinel file logic. On startup, call `POST /ready` with retry. On each image completion, call `POST /done` with the image as base64. If response is `{"done": true}`, exit.

**Step 1: Rewrite `docker/worker.py`**

```python
import base64
import json
import os
import time
from pathlib import Path
import requests

CALLBACK_URL = os.environ["CALLBACK_URL"]
CALLBACK_TOKEN = os.environ["CALLBACK_TOKEN"]
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

READY_RETRIES = 5
READY_INTERVAL = 300  # 5 minutes


def callback(path: str, data: dict) -> dict:
    resp = requests.post(f"{CALLBACK_URL}{path}", json=data, timeout=30)
    resp.raise_for_status()
    return resp.json()


def call_ready() -> dict:
    """Call /ready with retries. Returns response dict."""
    for attempt in range(1, READY_RETRIES + 1):
        try:
            print(f"Calling /ready (attempt {attempt}/{READY_RETRIES})...")
            return callback("/ready", {"token": CALLBACK_TOKEN})
        except Exception as e:
            print(f"  /ready failed: {e}")
            if attempt < READY_RETRIES:
                print(f"  Retrying in {READY_INTERVAL}s...")
                time.sleep(READY_INTERVAL)
    raise RuntimeError(f"/ready failed after {READY_RETRIES} attempts")


# Signal readiness and get first prompt
response = call_ready()

# Load model once
print("Loading model...")
import torch
from diffusers import FluxPipeline

pipe = FluxPipeline.from_pretrained("/model", torch_dtype=torch.bfloat16)
pipe = pipe.to("cuda")
print("Model loaded.")

while True:
    prompt = response.get("prompt")
    index = response.get("index", 0)

    if not prompt:
        print("No prompt in response, exiting.")
        break

    print(f"Generating image {index}: {prompt[:60]}")
    try:
        image = pipe(prompt, num_inference_steps=4, guidance_scale=0.0).images[0]
        img_path = OUTPUT_DIR / f"image_{index}.png"
        image.save(img_path)

        with open(img_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()

        print(f"Sending /done for index {index}...")
        response = callback("/done", {
            "token": CALLBACK_TOKEN,
            "index": index,
            "image_b64": image_b64,
        })

        if response.get("done"):
            print("All done. Exiting.")
            break

    except Exception as e:
        print(f"Error generating image {index}: {e}")
        # Report error and exit — orchestrator timeout will handle cleanup
        break
```

**Step 2: Commit**

```bash
git add docker/worker.py
git commit -m "feat: worker uses HTTP callbacks instead of sentinel files"
```

(This will be tested end-to-end in Task 6.)

---

### Task 5: orchestrator.py — rewrite around callback flow

**Files:**
- Modify: `flux_worker/orchestrator.py`

**Step 1: Rewrite `orchestrator.py`**

```python
import time
import traceback
import uuid
from pathlib import Path

from flux_worker.callback_server import CallbackServer
from flux_worker.config import load_config
from flux_worker.exceptions import UserError, VastAIError
from flux_worker.result import GenerateResult
from flux_worker.tunnel import Tunnel
from flux_worker import vastai

READY_TIMEOUT = 1800   # 30 min
IMAGE_TIMEOUT = 600    # 10 min per image
LOG_POLL_INTERVAL = 30 # seconds


def generate(
    prompts,
    output_dir="./output",
    vastai_api_key=None,
    ssh_key_path=None,
    max_gpu_price=None,
    min_vram_gb=None,
    min_cuda_version=None,
    disk_gb=None,
) -> GenerateResult:
    if isinstance(prompts, str):
        prompts = [prompts]

    config = None
    tunnel = Tunnel()
    server = None
    instance_id = None

    try:
        config = load_config(
            vastai_api_key=vastai_api_key,
            ssh_key_path=ssh_key_path,
            max_gpu_price=max_gpu_price,
            min_vram_gb=min_vram_gb,
            min_cuda_version=min_cuda_version,
            disk_gb=disk_gb,
            output_dir=output_dir,
        )
        config.output_dir.mkdir(parents=True, exist_ok=True)

        # Check for resumable instance
        resumable = vastai.find_resumable_instance(config.vastai_api_key)
        if resumable:
            instance_id = resumable["id"]
            token = (resumable.get("label") or "").replace("flux-worker-token:", "")
            print(f"Resuming existing instance {instance_id} (token: {token[:8]}...)")
        else:
            token = str(uuid.uuid4())

        # Start callback server + tunnel
        server = CallbackServer(token)
        port = server.start()
        print("Starting cloudflared tunnel...")
        callback_url = tunnel.start(port)
        print(f"Callback URL: {callback_url}")

        if not resumable:
            print(f"Finding GPU (max ${config.max_gpu_price}/hr, {config.min_vram_gb}GB VRAM)...")
            offer = vastai.find_offer(
                config.vastai_api_key,
                config.max_gpu_price,
                config.min_vram_gb,
                config.min_cuda_version,
            )
            print(f"Found: {offer['gpu_name']} @ ${offer['dph_total']:.3f}/hr (id={offer['id']})")
            print("Renting instance...")
            result = vastai.create_instance(
                config.vastai_api_key,
                offer["id"],
                disk_gb=config.disk_gb,
                callback_url=callback_url,
                callback_token=token,
                label=f"flux-worker-token:{token}",
            )
            instance_id = result["new_contract"]
            print(f"Instance {instance_id} created. Waiting for /ready (up to 30 min)...")

        paths = _run_job(config, server, instance_id, prompts)
        return GenerateResult(ok=True, images=paths)

    except UserError as e:
        return GenerateResult(ok=False, error_type="user_error", error_message=str(e))
    except VastAIError as e:
        return GenerateResult(ok=False, error_type="vastai_error", error_message=str(e))
    except Exception as e:
        tb = traceback.format_exc()
        return GenerateResult(ok=False, error_type="unexpected", error_message=str(e), traceback=tb, config=config)
    finally:
        if instance_id:
            print("Destroying instance...")
            try:
                vastai.destroy_instance(config.vastai_api_key, instance_id)
                print("Instance destroyed.")
            except Exception as e:
                print(f"Warning: failed to destroy instance: {e}")
        if server:
            server.stop()
        tunnel.stop()


def _run_job(config, server: CallbackServer, instance_id: int, prompts: list) -> list:
    paths = [None] * len(prompts)
    log_cursor = 0

    # Wait for /ready
    event = _wait_for_event(server, READY_TIMEOUT, config.vastai_api_key, instance_id)
    if event["type"] != "ready":
        raise RuntimeError(f"Expected 'ready' event, got: {event['type']}")

    print("GPU is ready. Sending first prompt...")
    server.send_response({"prompt": prompts[0], "index": 0})

    for i, prompt in enumerate(prompts):
        print(f"Waiting for image {i+1}/{len(prompts)}...")
        event = _wait_for_event(server, IMAGE_TIMEOUT, config.vastai_api_key, instance_id)

        if event["type"] != "done":
            raise RuntimeError(f"Expected 'done' event, got: {event['type']}")

        # Save image
        local_path = config.output_dir / f"image_{i}.png"
        local_path.write_bytes(event["image_bytes"])
        print(f"Saved: {local_path}")
        paths[i] = local_path

        # Send next prompt or signal done
        if i + 1 < len(prompts):
            server.send_response({"prompt": prompts[i + 1], "index": i + 1})
        else:
            server.send_response({"done": True})

    return paths


def _wait_for_event(server: CallbackServer, timeout: int, api_key: str, instance_id: int) -> dict:
    """Wait for next event from GPU, polling logs while waiting."""
    import queue as q
    deadline = time.time() + timeout
    last_log_poll = 0
    seen_log_lines = set()

    while time.time() < deadline:
        try:
            return server.events.get(timeout=LOG_POLL_INTERVAL)
        except q.Empty:
            pass

        # Poll logs
        now = time.time()
        if now - last_log_poll >= LOG_POLL_INTERVAL:
            logs = vastai.get_instance_logs(api_key, instance_id)
            for line in logs.splitlines():
                if line and line not in seen_log_lines:
                    print(f"  [gpu] {line}")
                    seen_log_lines.add(line)
            last_log_poll = now

    raise TimeoutError(f"Timed out after {timeout}s waiting for GPU callback")
```

**Step 2: Update `vastai.create_instance` signature** (from Task 3)

The orchestrator now calls:
```python
vastai.create_instance(
    api_key, offer_id,
    disk_gb=config.disk_gb,
    callback_url=callback_url,
    callback_token=token,
    label=f"flux-worker-token:{token}",
)
```

Make sure `create_instance` in `vastai.py` matches:

```python
def create_instance(api_key: str, offer_id: int, disk_gb: int,
                    callback_url: str, callback_token: str, label: str = "") -> dict:
    payload = {
        "client_id": "me",
        "image": DOCKER_IMAGE,
        "disk": disk_gb,
        "label": label,
        "env": {
            "CALLBACK_URL": callback_url,
            "CALLBACK_TOKEN": callback_token,
        },
    }
    resp = requests.put(
        f"{VASTAI_API}/asks/{offer_id}/",
        headers=_headers(api_key),
        json=payload,
    )
    _raise_for_status(resp)
    return resp.json()
```

**Step 3: Remove `ssh_key_path` from `config.py`**

The `ssh_key_path` field is no longer used. Remove it from `Config` dataclass and `load_config`. Also remove the SSH key existence check and the `UserError` for missing key.

**Step 4: Commit**

```bash
git add flux_worker/orchestrator.py flux_worker/vastai.py flux_worker/config.py
git commit -m "feat: callback-driven orchestrator, drop SSH"
```

---

### Task 6: End-to-end test

**Step 1: Verify cloudflared is installed**

```bash
cloudflared --version
```
If missing: `brew install cloudflare/cloudflare/cloudflared`

**Step 2: Run the test**

```bash
uv run flux-worker generate "a red cat sitting on a cloud"
```

**Watch for these milestones in output:**
1. `Starting cloudflared tunnel...` then `Callback URL: https://xxxx.trycloudflare.com`
2. `Found: RTX ... @ $0.0xx/hr`
3. `Instance XXXXXXX created. Waiting for /ready (up to 30 min)...`
4. `[gpu]` log lines showing image pull progress
5. `GPU is ready. Sending first prompt...`
6. `[gpu]` lines showing model load + generation
7. `Saved: ./output/image_0.png`
8. `Instance destroyed.`

**Step 3: Verify output**

```bash
open output/image_0.png
```

**Step 4: If something goes wrong**

- Check `[gpu]` log lines for errors
- If stuck at `/ready` for >5 min, check if CALLBACK_URL is reachable: `curl <callback_url>/ready` from another terminal (expect 405 or similar, not connection refused)
- If instance not destroyed: `uv run python -c "from flux_worker import vastai; import os; from dotenv import load_dotenv; load_dotenv(); vastai.destroy_instance(os.environ['VASTAI_API_KEY'], <id>)"`

**Step 5: Commit**

```bash
git add -p  # review any leftover changes
git commit -m "fix: any issues found during e2e test"
```

---

### Task 7: Build and push Docker image

**Step 1: Push to trigger CI**

```bash
git push
```

**Step 2: Monitor build**

```bash
gh run watch
```

Expected: build succeeds, new image pushed to `ghcr.io/ddecoene/flux-worker:latest`

**Step 3: Run e2e test again with fresh image**

Repeat Task 6 to confirm the new Docker image (with callback worker) works end-to-end.
