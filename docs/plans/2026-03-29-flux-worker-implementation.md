# flux-worker Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python package that generates images with FLUX.1-schnell on ephemeral Vast.ai GPUs, with a clean `generate(prompts) -> list[Path]` API and a CLI wrapper.

**Architecture:** Python client orchestrates the full Vast.ai lifecycle — find GPU, rent, run Docker worker, poll and progressively download images via SSH, destroy. The Docker worker runs on the GPU and generates images sequentially, writing per-image sentinels so the client can download as each finishes.

**Tech Stack:** Python 3.10+, Click, paramiko (SSH), requests (Vast.ai REST API), python-dotenv, UV for dev. No pytest — manual live testing against real Vast.ai only.

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `flux_worker/__init__.py`
- Create: `flux_worker/cli.py`
- Create: `flux_worker/orchestrator.py`
- Create: `flux_worker/vastai.py`
- Create: `.env.example`

**Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "flux-worker"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "click>=8.0",
    "python-dotenv>=1.0",
    "requests>=2.31",
    "paramiko>=3.0",
]

[project.scripts]
flux-worker = "flux_worker.cli:cli"
```

**Step 2: Create empty module files**

`flux_worker/__init__.py` — just a pass-through for now:
```python
from flux_worker.orchestrator import generate

__all__ = ["generate"]
```

`flux_worker/orchestrator.py`:
```python
# placeholder
def generate(prompts, **kwargs):
    raise NotImplementedError
```

`flux_worker/vastai.py`:
```python
# placeholder
```

`flux_worker/cli.py`:
```python
import click

@click.group()
def cli():
    pass
```

**Step 3: Create `.env.example`**

```
VASTAI_API_KEY=
SSH_KEY_PATH=~/.ssh/id_ed25519
MAX_GPU_PRICE=0.50
MIN_VRAM_GB=16
MIN_CUDA_VERSION=12.0
DISK_GB=50
```

**Step 4: Install in dev mode**

```bash
uv sync
```

Expected: resolves dependencies, installs package. `flux-worker --help` should work.

**Step 5: Commit**

```bash
git add pyproject.toml flux_worker/ .env.example
git commit -m "feat: project scaffold"
```

---

### Task 2: Config loading

**Files:**
- Create: `flux_worker/config.py`

Config is loaded once at the start of `generate()`. It reads from kwargs first, then env vars, then `.env` file, then falls back to defaults. Fail fast if `VASTAI_API_KEY` is missing or SSH key file not found.

**Step 1: Write `flux_worker/config.py`**

```python
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    vastai_api_key: str
    ssh_key_path: Path
    max_gpu_price: float
    min_vram_gb: int
    min_cuda_version: float
    disk_gb: int
    output_dir: Path

def load_config(
    vastai_api_key=None,
    ssh_key_path=None,
    max_gpu_price=None,
    min_vram_gb=None,
    min_cuda_version=None,
    disk_gb=None,
    output_dir="./output",
) -> Config:
    api_key = vastai_api_key or os.environ.get("VASTAI_API_KEY")
    if not api_key:
        raise ValueError("VASTAI_API_KEY is required. Set it in .env or pass vastai_api_key=.")

    # SSH key: try explicit, then env, then id_ed25519, then id_rsa
    if ssh_key_path:
        key = Path(ssh_key_path).expanduser()
    elif os.environ.get("SSH_KEY_PATH"):
        key = Path(os.environ["SSH_KEY_PATH"]).expanduser()
    else:
        key = Path("~/.ssh/id_ed25519").expanduser()
        if not key.exists():
            key = Path("~/.ssh/id_rsa").expanduser()

    if not key.exists():
        raise FileNotFoundError(
            f"SSH key not found at {key}. "
            "Create one or set SSH_KEY_PATH. "
            "The key must be registered in your Vast.ai account settings."
        )

    return Config(
        vastai_api_key=api_key,
        ssh_key_path=key,
        max_gpu_price=float(max_gpu_price or os.environ.get("MAX_GPU_PRICE", 0.50)),
        min_vram_gb=int(min_vram_gb or os.environ.get("MIN_VRAM_GB", 16)),
        min_cuda_version=float(min_cuda_version or os.environ.get("MIN_CUDA_VERSION", 12.0)),
        disk_gb=int(disk_gb or os.environ.get("DISK_GB", 50)),
        output_dir=Path(output_dir),
    )
```

**Step 2: Verify manually**

```python
# python -c "from flux_worker.config import load_config; print(load_config())"
# Should raise ValueError if VASTAI_API_KEY not set
# Should raise FileNotFoundError if SSH key missing
```

**Step 3: Commit**

```bash
git add flux_worker/config.py
git commit -m "feat: config loading with validation"
```

---

### Task 3: Vast.ai API — find GPU offer

**Files:**
- Modify: `flux_worker/vastai.py`

**Step 1: Write `find_offer()` in `vastai.py`**

```python
import requests

VASTAI_API = "https://console.vast.ai/api/v0"

def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}

def find_offer(api_key: str, max_price: float, min_vram_gb: int, min_cuda: float) -> dict:
    """Return cheapest available offer meeting requirements, or raise."""
    params = {
        "q": {
            "rentable": {"eq": True},
            "gpu_ram": {"gte": min_vram_gb * 1024},  # MB
            "dph_total": {"lte": max_price},
            "cuda_vers": {"gte": min_cuda},
            "gpu_name": {"notin": ["Tesla V100", "Tesla V100-SXM2-16GB", "Tesla V100-PCIE-16GB"]},
            "order": [["dph_total", "asc"]],
            "limit": 10,
        }
    }
    resp = requests.get(f"{VASTAI_API}/bundles", headers=_headers(api_key), params={"q": str(params["q"])})
    resp.raise_for_status()
    offers = resp.json().get("offers", [])
    if not offers:
        raise RuntimeError(
            f"No GPU available under ${max_price}/hr with {min_vram_gb}GB VRAM and CUDA {min_cuda}+. "
            "Try increasing --max-gpu-price."
        )
    return offers[0]
```

**Step 2: Verify manually**

```python
# python -c "
# from flux_worker.vastai import find_offer
# import os; from dotenv import load_dotenv; load_dotenv()
# offer = find_offer(os.environ['VASTAI_API_KEY'], 0.50, 16, 12.0)
# print(offer['id'], offer['gpu_name'], offer['dph_total'])
# "
```

Expected: prints an offer id, GPU name, and price.

**Step 3: Commit**

```bash
git add flux_worker/vastai.py
git commit -m "feat: vastai find_offer"
```

---

### Task 4: Vast.ai API — create and destroy instance

**Files:**
- Modify: `flux_worker/vastai.py`

**Step 1: Add `create_instance()` and `destroy_instance()`**

```python
import json

DOCKER_IMAGE = "ghcr.io/ddecoene/flux-worker:latest"

def create_instance(api_key: str, offer_id: int, prompts: list[str], disk_gb: int) -> dict:
    """Rent the offer and start the worker. Returns instance dict."""
    payload = {
        "client_id": "me",
        "image": DOCKER_IMAGE,
        "disk": disk_gb,
        "env": {
            "PROMPTS": json.dumps(prompts),
        },
        "onstart": (
            "docker run --gpus all "
            "-e PROMPTS=\"$PROMPTS\" "
            "-v /output:/output "
            f"{DOCKER_IMAGE}"
        ),
    }
    resp = requests.put(
        f"{VASTAI_API}/asks/{offer_id}/",
        headers=_headers(api_key),
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()

def get_instance(api_key: str, instance_id: int) -> dict | None:
    """Return instance dict or None if not found."""
    resp = requests.get(f"{VASTAI_API}/instances/", headers=_headers(api_key))
    resp.raise_for_status()
    instances = resp.json().get("instances", [])
    for inst in instances:
        if inst["id"] == instance_id:
            return inst
    return None

def destroy_instance(api_key: str, instance_id: int) -> None:
    resp = requests.delete(f"{VASTAI_API}/instances/{instance_id}/", headers=_headers(api_key))
    resp.raise_for_status()
```

**Step 2: Commit**

```bash
git add flux_worker/vastai.py
git commit -m "feat: vastai create/destroy instance"
```

---

### Task 5: SSH operations

**Files:**
- Modify: `flux_worker/vastai.py`

The client needs to: wait for SSH to be ready, check if a file exists, download a file.

**Step 1: Add SSH helpers**

```python
import time
import paramiko

def _ssh_client(host: str, port: int, key_path) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        port=port,
        username="root",
        key_filename=str(key_path),
        timeout=10,
    )
    return client

def wait_for_ssh(host: str, port: int, key_path, timeout: int = 300) -> None:
    """Poll until SSH is accepting connections, or raise on timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            client = _ssh_client(host, port, key_path)
            client.close()
            time.sleep(30)  # daemon needs time to stabilize after first connect
            return
        except Exception:
            time.sleep(5)
    raise TimeoutError(f"SSH not ready after {timeout}s")

def file_exists_ssh(host: str, port: int, key_path, remote_path: str) -> bool:
    client = _ssh_client(host, port, key_path)
    try:
        _, stdout, _ = client.exec_command(f"test -f {remote_path} && echo yes || echo no")
        return stdout.read().decode().strip() == "yes"
    finally:
        client.close()

def download_file_ssh(host: str, port: int, key_path, remote_path: str, local_path) -> None:
    client = _ssh_client(host, port, key_path)
    try:
        sftp = client.open_sftp()
        sftp.get(remote_path, str(local_path))
        sftp.close()
    finally:
        client.close()

def read_file_ssh(host: str, port: int, key_path, remote_path: str) -> str:
    client = _ssh_client(host, port, key_path)
    try:
        _, stdout, _ = client.exec_command(f"cat {remote_path}")
        return stdout.read().decode().strip()
    finally:
        client.close()
```

**Step 2: Commit**

```bash
git add flux_worker/vastai.py
git commit -m "feat: ssh helpers (wait, check, download)"
```

---

### Task 6: Orchestrator

**Files:**
- Modify: `flux_worker/orchestrator.py`

This is the main flow. Ties everything together.

**Step 1: Write `orchestrator.py`**

```python
import time
from pathlib import Path
from flux_worker.config import load_config
from flux_worker import vastai

def generate(
    prompts,
    output_dir="./output",
    vastai_api_key=None,
    ssh_key_path=None,
    max_gpu_price=None,
    min_vram_gb=None,
    min_cuda_version=None,
    disk_gb=None,
) -> list[Path]:
    if isinstance(prompts, str):
        prompts = [prompts]

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

    print(f"Finding GPU (max ${config.max_gpu_price}/hr, {config.min_vram_gb}GB VRAM)...")
    offer = vastai.find_offer(
        config.vastai_api_key,
        config.max_gpu_price,
        config.min_vram_gb,
        config.min_cuda_version,
    )
    print(f"Found: {offer['gpu_name']} @ ${offer['dph_total']:.3f}/hr (id={offer['id']})")

    instance_id = None
    try:
        print("Renting instance...")
        result = vastai.create_instance(
            config.vastai_api_key,
            offer["id"],
            prompts,
            config.disk_gb,
        )
        instance_id = result["new_contract"]
        print(f"Instance {instance_id} created. Waiting for SSH...")

        # Poll until running
        host, port = _wait_for_running(config.vastai_api_key, instance_id)
        vastai.wait_for_ssh(host, port, config.ssh_key_path)
        print("SSH ready. Generating images...")

        paths = _poll_and_download(config, host, port, prompts, instance_id)
        return paths

    finally:
        if instance_id:
            print(f"Destroying instance {instance_id}...")
            try:
                vastai.destroy_instance(config.vastai_api_key, instance_id)
                print("Instance destroyed.")
            except Exception as e:
                print(f"Warning: failed to destroy instance {instance_id}: {e}")


def _wait_for_running(api_key: str, instance_id: int, timeout: int = 300):
    """Poll until instance is running, return (host, port)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        inst = vastai.get_instance(api_key, instance_id)
        if inst and inst.get("actual_status") == "running":
            return inst["ssh_host"], inst["ssh_port"]
        time.sleep(5)
    raise TimeoutError(f"Instance {instance_id} did not reach running state after {timeout}s")


def _poll_and_download(config, host: str, port: int, prompts: list[str], instance_id: int) -> list[Path]:
    """Poll for done_N sentinels, download image_N.png as each appears."""
    paths = [None] * len(prompts)
    remaining = set(range(len(prompts)))

    while remaining:
        for i in list(remaining):
            sentinel = f"/output/done_{i}"
            if vastai.file_exists_ssh(host, port, config.ssh_key_path, sentinel):
                status = vastai.read_file_ssh(host, port, config.ssh_key_path, sentinel)
                if status != "ok":
                    raise RuntimeError(f"Worker failed on prompt {i}: {status}")
                local_path = config.output_dir / f"image_{i}.png"
                print(f"Downloading image {i+1}/{len(prompts)}...")
                vastai.download_file_ssh(host, port, config.ssh_key_path, f"/output/image_{i}.png", local_path)
                print(f"Saved: {local_path}")
                paths[i] = local_path
                remaining.remove(i)
        if remaining:
            time.sleep(5)

    return paths
```

**Step 2: Commit**

```bash
git add flux_worker/orchestrator.py
git commit -m "feat: orchestrator — full generate() flow with progressive download"
```

---

### Task 7: CLI

**Files:**
- Modify: `flux_worker/cli.py`

Thin wrapper. All logic stays in `generate()`.

**Step 1: Write `cli.py`**

```python
import json
import click
from flux_worker.orchestrator import generate

@click.group()
def cli():
    pass

@cli.command()
@click.argument("prompts", nargs=-1)
@click.option("--prompts-file", type=click.Path(exists=True), help="JSON file with list of prompts")
@click.option("--output", default="./output", show_default=True, help="Output directory")
@click.option("--vastai-key", envvar="VASTAI_API_KEY", help="Vast.ai API key")
@click.option("--max-gpu-price", type=float, envvar="MAX_GPU_PRICE", help="Max $/hr (default: 0.50)")
@click.option("--min-vram-gb", type=int, envvar="MIN_VRAM_GB", help="Min VRAM in GB (default: 16)")
@click.option("--min-cuda-version", type=float, envvar="MIN_CUDA_VERSION", help="Min CUDA version (default: 12.0)")
@click.option("--disk-gb", type=int, envvar="DISK_GB", help="Disk GB for instance (default: 50)")
@click.option("--ssh-key-path", envvar="SSH_KEY_PATH", help="SSH private key path")
def generate_cmd(prompts, prompts_file, output, vastai_key, max_gpu_price, min_vram_gb, min_cuda_version, disk_gb, ssh_key_path):
    """Generate images from one or more prompts."""
    if prompts_file:
        with open(prompts_file) as f:
            all_prompts = json.load(f)
    else:
        all_prompts = list(prompts)

    if not all_prompts:
        raise click.UsageError("Provide at least one prompt or --prompts-file.")

    paths = generate(
        prompts=all_prompts,
        output_dir=output,
        vastai_api_key=vastai_key,
        max_gpu_price=max_gpu_price,
        min_vram_gb=min_vram_gb,
        min_cuda_version=min_cuda_version,
        disk_gb=disk_gb,
        ssh_key_path=ssh_key_path,
    )
    for p in paths:
        click.echo(str(p))

cli.add_command(generate_cmd, name="generate")
```

**Step 2: Verify**

```bash
flux-worker --help
flux-worker generate --help
```

**Step 3: Commit**

```bash
git add flux_worker/cli.py
git commit -m "feat: CLI — click wrapper around generate()"
```

---

### Task 8: Docker worker

**Files:**
- Create: `docker/worker.py`
- Create: `docker/Dockerfile`

**Step 1: Write `docker/worker.py`**

```python
import json
import os
from pathlib import Path

output_dir = Path(os.environ.get("OUTPUT_DIR", "/output"))
output_dir.mkdir(parents=True, exist_ok=True)

prompts = json.loads(os.environ["PROMPTS"])

import torch
from diffusers import FluxPipeline

pipe = FluxPipeline.from_pretrained(
    "/model",
    torch_dtype=torch.bfloat16,
)
pipe = pipe.to("cuda")

for i, prompt in enumerate(prompts):
    print(f"Generating {i+1}/{len(prompts)}: {prompt[:60]}")
    try:
        image = pipe(
            prompt,
            num_inference_steps=4,
            guidance_scale=0.0,
        ).images[0]
        image.save(output_dir / f"image_{i}.png")
        (output_dir / f"done_{i}").write_text("ok")
        print(f"Done {i+1}/{len(prompts)}")
    except Exception as e:
        (output_dir / f"done_{i}").write_text(str(e))
        print(f"Error on prompt {i}: {e}")
```

**Step 2: Write `docker/Dockerfile`**

```dockerfile
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y python3 python3-pip git && rm -rf /var/lib/apt/lists/*

RUN pip3 install torch --index-url https://download.pytorch.org/whl/cu121
RUN pip3 install diffusers transformers accelerate sentencepiece protobuf

ARG HF_TOKEN
RUN python3 -c "
from huggingface_hub import snapshot_download
snapshot_download(
    'black-forest-labs/FLUX.1-schnell',
    local_dir='/model',
    token='${HF_TOKEN}',
)
"

COPY worker.py /worker.py

CMD ["python3", "/worker.py"]
```

**Step 3: Commit**

```bash
git add docker/
git commit -m "feat: docker worker — sequential generation with per-image sentinels"
```

---

### Task 9: GitHub Actions — build and push Docker image

**Files:**
- Create: `.github/workflows/build.yml`

**Step 1: Write `.github/workflows/build.yml`**

```yaml
name: Build and push Docker image

on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4

      - name: Log in to ghcr.io
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: docker/
          push: true
          build-args: |
            HF_TOKEN=${{ secrets.HF_TOKEN }}
          tags: |
            ghcr.io/ddecoene/flux-worker:latest
            ghcr.io/ddecoene/flux-worker:sha-${{ github.sha }}
```

**Step 2: Commit**

```bash
git add .github/
git commit -m "ci: build and push Docker image on push to main"
```

---

### Task 10: Live end-to-end test

No automated tests — verify manually against real Vast.ai.

**Step 1: Set up `.env`**

```bash
cp .env.example .env
# Fill in VASTAI_API_KEY
```

**Step 2: Run single prompt**

```bash
flux-worker generate "a cyclist at golden hour in the Flemish polders"
```

Expected:
- Prints GPU found, instance ID, SSH ready, generating, downloading
- Saves `./output/image_0.png`
- Destroys instance

**Step 3: Run batch**

```bash
flux-worker generate "a cyclist at golden hour" "a runner in the rain"
```

Expected: `image_0.png` downloads before `image_1.png` is done generating.

**Step 4: Test Python API**

```python
from flux_worker import generate
paths = generate(["a cyclist at golden hour", "a runner in the rain"])
print(paths)
```

**Step 5: Verify instance is destroyed**

Check [console.vast.ai](https://console.vast.ai) — no running instances.

**Step 6: Tag release**

```bash
git tag v0.1.0
git push origin v0.1.0
```
